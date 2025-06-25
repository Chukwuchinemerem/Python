from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Sum, Q
from decimal import Decimal
import requests
from .models import (
    User, InvestmentTier, CryptoCurrency, Investment, 
    Transaction, DepositRequest, WithdrawalRequest, CryptoPrice
)

from django.contrib.auth.decorators import user_passes_test
from datetime import timedelta
from django.core.mail import send_mail
from django.views.decorators.csrf import csrf_exempt
import json



# Your existing models imports
from .models import *

# Landing page views
def home(request):
    return render(request, "landing/index.html")

def about(request):
    return render(request, "landing/about.html")

def faq(request):
    return render(request, "landing/faq.html")

def package(request):
    return render(request, "landing/package.html")

def privacy(request):
    return render(request, "landing/privacy.html")

def terms(request):
    return render(request, "landing/rules.html")

def contact(request):
    return render(request, "landing/support.html")

def signin(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password')
    
    return render(request, "landing/login.html")

def signup(request):
    if request.method == 'POST':
        # Get form data
        first_name = request.POST.get('fname')
        last_name = request.POST.get('lname')
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        password_confirm = request.POST.get('password_confirm')
        phone = request.POST.get('phone')
        country = request.POST.get('country')
        
        # Validation
        if password != password_confirm:
            messages.error(request, 'Passwords do not match')
            return render(request, "landing/register.html")
        
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists')
            return render(request, "landing/register.html")
        
        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already exists')
            return render(request, "landing/register.html")
        
        # Create user
        try:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                country=country
            )
            messages.success(request, 'Account created successfully! Please login.')
            return redirect('signin')
        except Exception as e:
            messages.error(request, 'Error creating account. Please try again.')
    
    return render(request, "landing/register.html")

@login_required
def user_logout(request):
    logout(request)
    return redirect('home')



@login_required
def dashboard(request):
    user = request.user
    
    # Get user statistics
    active_investments = Investment.objects.filter(user=user, is_completed=False)
    
    # Update crypto prices
    update_crypto_prices()
    
    context = {
        'user': user,
        'total_deposited': user.total_deposited,
        'total_profit': user.current_total_profit,  # Use dynamic calculation
        'total_withdrawn': user.current_total_withdrawn,  # Use dynamic calculation
        'total_balance': user.current_balance,  # Use dynamic calculation
        'active_investments': active_investments,
        'recent_transactions': user.transactions.all()[:5],
        'crypto_prices': CryptoPrice.objects.filter(cryptocurrency__symbol__in=['BTC', 'ETH', 'SOL', 'TON'])[:4]

    }
    
    return render(request, 'invest/dashboard.html', context)



@login_required
def deposit(request):
    # Ensure investment tiers exist
    def create_investment_tiers():
        tiers_data = [
            {
                'name': 'ROYAL',
                'roi_percentage': Decimal('20.00'),
                'duration_hours': 24,
                'min_investment': Decimal('100.00'),
                'max_investment': Decimal('4999.00'),
                'referral_bonus': Decimal('5.00'),
                'incentive_description': '24/7 Support',
                'is_active': True
            },
            {
                'name': 'ELITE',
                'roi_percentage': Decimal('35.00'),
                'duration_hours': 24,
                'min_investment': Decimal('5000.00'),
                'max_investment': Decimal('49999.00'),
                'referral_bonus': Decimal('5.00'),
                'incentive_description': 'Crypto Ebook Included',
                'is_active': True
            },
            {
                'name': 'EXECUTIVE',
                'roi_percentage': Decimal('100.00'),
                'duration_hours': 24,
                'min_investment': Decimal('50000.00'),
                'max_investment': None,  # Unlimited
                'referral_bonus': Decimal('5.00'),
                'incentive_description': '$100 Bonus Included',
                'is_active': True
            }
        ]
        
        for tier_data in tiers_data:
            InvestmentTier.objects.get_or_create(
                name=tier_data['name'],
                defaults=tier_data
            )
    
    if request.method == 'POST':
        try:
            # Ensure tiers exist before processing
            create_investment_tiers()
            
            amount = Decimal(request.POST.get('amount', 0))
            crypto_id = request.POST.get('cryptocurrency')
            selected_tier = request.POST.get('selected_tier')
            transaction_id = request.POST.get('transaction_id', '').strip()
            
            # Validate inputs
            if not all([amount, crypto_id, selected_tier, transaction_id]):
                messages.error(request, 'All fields are required.')
                return redirect('deposit')
            
            if amount <= 0:
                messages.error(request, 'Please enter a valid amount.')
                return redirect('deposit')
            
            # Get cryptocurrency
            try:
                cryptocurrency = CryptoCurrency.objects.get(id=crypto_id)
            except CryptoCurrency.DoesNotExist:
                messages.error(request, 'Selected cryptocurrency not found.')
                return redirect('deposit')
            
            # Check if cryptocurrency has wallet address
            if not cryptocurrency.wallet_address:
                messages.error(request, f'{cryptocurrency.name} wallet address is not configured. Please contact admin.')
                return redirect('deposit')
            
            # Get investment tier by name
            tier_mapping = {
                'royal': 'ROYAL',
                'elite': 'ELITE', 
                'executive': 'EXECUTIVE'
            }
            tier_name = tier_mapping.get(selected_tier.lower())
            
            if not tier_name:
                messages.error(request, 'Invalid investment tier selected.')
                return redirect('deposit')
            
            try:
                investment_tier = InvestmentTier.objects.get(name=tier_name)
            except InvestmentTier.DoesNotExist:
                messages.error(request, f'Investment tier {tier_name} not found.')
                return redirect('deposit')
            
            # Validate amount against tier limits
            if amount < investment_tier.min_investment:
                messages.error(request, f'Minimum investment for {investment_tier.name} tier is ${investment_tier.min_investment:,.2f}')
                return redirect('deposit')
            
            if investment_tier.max_investment and amount > investment_tier.max_investment:
                messages.error(request, f'Maximum investment for {investment_tier.name} tier is ${investment_tier.max_investment:,.2f}')
                return redirect('deposit')
            
            # Check for duplicate transaction ID
            if Transaction.objects.filter(transaction_id=transaction_id).exists():
                messages.error(request, 'This transaction ID has already been used.')
                return redirect('deposit')
            
            # Create deposit request
            deposit_request = DepositRequest.objects.create(
                user=request.user,
                amount=amount,
                cryptocurrency=cryptocurrency,
                investment_tier=investment_tier,
                transaction_id=transaction_id,
                wallet_address_used=cryptocurrency.wallet_address
            )
            
            # Create transaction record
            Transaction.objects.create(
                user=request.user,
                transaction_type='DEPOSIT',
                amount=amount,
                cryptocurrency=cryptocurrency,
                transaction_id=transaction_id,
                investment_tier=investment_tier,
                status='PENDING'
            )
            
            messages.success(request, 'Deposit request submitted successfully! Please wait for admin approval.')
            return redirect('dashboard')
            
        except Exception as e:
            messages.error(request, f'Error processing deposit request: {str(e)}')
            return redirect('deposit')
    
    # GET request - display form
    try:
        # Ensure tiers exist
        create_investment_tiers()
        
        context = {
            'cryptocurrencies': CryptoCurrency.objects.filter(is_active=True),
            'investment_tiers': InvestmentTier.objects.filter(is_active=True).order_by('min_investment'),
        }
        
        # If no cryptocurrencies exist, show warning
        if not context['cryptocurrencies'].exists():
            messages.warning(request, 'No cryptocurrencies are currently available. Please contact admin.')
        
        return render(request, 'invest/deposit.html', context)
        
    except Exception as e:
        messages.error(request, f'Error loading deposit page: {str(e)}')
        return redirect('dashboard')



@login_required
def withdraw(request):
    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount', 0))
        crypto_id = request.POST.get('cryptocurrency')
        wallet_address = request.POST.get('wallet_address')
        
        try:
            # Check if user has sufficient balance
            if amount > request.user.balance:
                messages.error(request, 'Insufficient balance')
                return redirect('withdraw')
            
            cryptocurrency = CryptoCurrency.objects.get(id=crypto_id)
            
            # Deduct amount from user balance immediately
            user = request.user
            user.balance -= amount
            user.save()
            
            # Create withdrawal request
            withdrawal_request = WithdrawalRequest.objects.create(
                user=user,
                amount=amount,
                cryptocurrency=cryptocurrency,
                wallet_address=wallet_address
            )
            
            # Create transaction record
            Transaction.objects.create(
                user=user,
                transaction_type='WITHDRAWAL',
                amount=amount,
                cryptocurrency=cryptocurrency,
                wallet_address=wallet_address,
                status='PENDING'
            )
            
            messages.success(request, 'Withdrawal request submitted successfully! Please wait for admin approval.')
            return redirect('dashboard')
            
        except Exception as e:
            messages.error(request, 'Error processing withdrawal request. Please try again.')
    
    context = {
        'cryptocurrencies': CryptoCurrency.objects.filter(is_active=True),
        'user_balance': request.user.balance,
    }
    
    return render(request, 'invest/withdraw.html', context)

@login_required
def history(request):
    """Enhanced history view with correct statistics"""
    from django.db.models import Count, Q
    
    # Get all user data
    transactions = request.user.transactions.all().order_by('-created_at')
    deposit_requests = request.user.deposit_requests.all().order_by('-created_at')
    withdrawal_requests = request.user.withdrawal_requests.all().order_by('-created_at')
    
    # Calculate correct statistics
    stats = {
        'total_deposits': deposit_requests.count(),
        'total_withdrawals': withdrawal_requests.count(),
        'pending_transactions': transactions.filter(status='PENDING').count(),
        'completed_transactions': transactions.filter(status__in=['APPROVED', 'COMPLETED']).count()
    }
    
    context = {
        'transactions': transactions,
        'deposit_requests': deposit_requests,
        'withdrawal_requests': withdrawal_requests,
        'stats': stats,
    }
    
    return render(request, 'invest/history.html', context)

@login_required
def profile(request):
    if request.method == 'POST':
        # Handle AJAX password change
        if request.headers.get('Content-Type') == 'application/json':
            try:
                data = json.loads(request.body)
                current_password = data.get('current_password')
                new_password = data.get('new_password')
                
                # Verify current password
                if not request.user.check_password(current_password):
                    return JsonResponse({'success': False, 'message': 'Current password is incorrect'})
                
                # Validate new password length
                if len(new_password) < 8:
                    return JsonResponse({'success': False, 'message': 'Password must be at least 8 characters long'})
                
                # Set new password
                request.user.set_password(new_password)
                request.user.save()
                
                # Keep user logged in after password change
                update_session_auth_hash(request, request.user)
                
                return JsonResponse({'success': True, 'message': 'Password changed successfully'})
                
            except json.JSONDecodeError:
                return JsonResponse({'success': False, 'message': 'Invalid request'})
            except Exception as e:
                return JsonResponse({'success': False, 'message': 'An error occurred while changing password'})
        
        # Handle regular form submission for profile update
        else:
            try:
                # Update user information
                request.user.first_name = request.POST.get('first_name', '')
                request.user.last_name = request.POST.get('last_name', '')
                request.user.email = request.POST.get('email', '')
                
                # Update additional fields if they exist in your user model
                if hasattr(request.user, 'phone'):
                    request.user.phone = request.POST.get('phone', '')
                if hasattr(request.user, 'country'):
                    request.user.country = request.POST.get('country', '')
                
                request.user.save()
                
                # Handle profile picture if uploaded
                if 'profile_picture' in request.FILES:
                    # Handle profile picture upload logic here
                    pass
                
                return JsonResponse({'success': True, 'message': 'Profile updated successfully'})
                
            except Exception as e:
                return JsonResponse({'success': False, 'message': 'An error occurred while updating profile'})
    
    return render(request, 'invest/profile.html', {'user': request.user})

# AJAX view for getting wallet address
@login_required
def get_wallet_address(request):
    if request.method == 'GET':
        crypto_id = request.GET.get('crypto_id')
        try:
            cryptocurrency = CryptoCurrency.objects.get(id=crypto_id)
            return JsonResponse({
                'success': True,
                'wallet_address': cryptocurrency.wallet_address,
                'crypto_name': cryptocurrency.name,
                'crypto_symbol': cryptocurrency.symbol
            })
        except CryptoCurrency.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Cryptocurrency not found'})
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})

# Function to update crypto prices (can be called via management command or celery task)
def update_crypto_prices():
    """Fetch and update crypto prices from CoinGecko API"""
    try:
        # CoinGecko free API endpoint
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            'ids': 'bitcoin,ethereum,solana,the-open-network',
            'vs_currencies': 'usd',
            'include_24hr_change': 'true'
        }
        
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        # Mapping of API IDs to our symbols
        crypto_mapping = {
            'bitcoin': 'BTC',
            'ethereum': 'ETH', 
            'solana': 'SOL',
            'the-open-network': 'TON'
        }
        
        for api_id, symbol in crypto_mapping.items():
            if api_id in data:
                crypto, created = CryptoCurrency.objects.get_or_create(
                    symbol=symbol,
                    defaults={'name': symbol, 'wallet_address': '', 'is_active': True}
                )
                
                CryptoPrice.objects.update_or_create(
                    cryptocurrency=crypto,
                    defaults={
                        'price_usd': Decimal(str(data[api_id]['usd'])),
                        'change_24h': Decimal(str(data[api_id].get('usd_24h_change', 0))),
                        'last_updated': timezone.now()
                    }
                )
    except Exception as e:
        print(f"Error updating crypto prices: {e}")
        pass
# ==============================================



def is_admin(user):
    return user.is_staff or user.is_superuser

# ADMIN VIEWS
@user_passes_test(is_admin)
def admin_dashboard(request):
    """Admin dashboard with real data"""
    context = {
        'total_users': User.objects.filter(is_staff=False).count(),
        'pending_deposits': DepositRequest.objects.filter(status='PENDING').count(),
        'pending_withdrawals': WithdrawalRequest.objects.filter(status='PENDING').count(),
        'total_deposits_today': DepositRequest.objects.filter(
            created_at__date=timezone.now().date(),
            status='APPROVED'
        ).aggregate(total=models.Sum('amount'))['total'] or 0,
        'recent_deposits': DepositRequest.objects.select_related('user', 'cryptocurrency', 'investment_tier').order_by('-created_at')[:5],
    }
    return render(request, 'admins/admin_dashboard.html', context)

@user_passes_test(is_admin)
def admin_deposits(request):
    """Manage deposit requests with enhanced statistics and filtering"""
    if request.method == 'POST':
        deposit_id = request.POST.get('deposit_id')
        action = request.POST.get('action')
        
        try:
            deposit = get_object_or_404(DepositRequest, id=deposit_id)
            
            if action == 'approve':
                # Update deposit status
                deposit.status = 'APPROVED'
                deposit.processed_at = timezone.now()
                deposit.processed_by = request.user
                deposit.save()
                
                # Update user balance and stats using the new method
                user = deposit.user
                user.update_balances()  # This will recalculate all balances
                
                # Create investment record
                Investment.objects.create(
                    user=user,
                    tier=deposit.investment_tier,
                    amount=deposit.amount,
                    start_date=timezone.now(),
                    end_date=timezone.now() + timedelta(hours=deposit.investment_tier.duration_hours)
                )
                
                # Update transaction status
                Transaction.objects.filter(
                    user=user,
                    transaction_type='DEPOSIT',
                    amount=deposit.amount,
                    status='PENDING',
                    transaction_id=deposit.transaction_id
                ).update(
                    status='APPROVED',
                    processed_at=timezone.now()
                )
                
                # Handle referral bonus if user was referred
                if user.referred_by:
                    referral_bonus = (deposit.amount * deposit.investment_tier.referral_bonus) / 100
                    referrer = user.referred_by
                    
                    # Create referral bonus transaction
                    Transaction.objects.create(
                        user=referrer,
                        transaction_type='REFERRAL',
                        amount=referral_bonus,
                        status='COMPLETED',
                        notes=f'Referral bonus from {user.username} deposit'
                    )
                    
                    # Update referrer's balances
                    referrer.update_balances()
                
                messages.success(request, f'Deposit of ${deposit.amount} approved for {user.username}')   
            elif action == 'reject':
                deposit.status = 'REJECTED'
                deposit.processed_at = timezone.now()
                deposit.processed_by = request.user
                deposit.save()
                
                # Update transaction status
                Transaction.objects.filter(
                    user=deposit.user,
                    transaction_type='DEPOSIT',
                    amount=deposit.amount,
                    status='PENDING',
                    transaction_id=deposit.transaction_id
                ).update(
                    status='REJECTED',
                    processed_at=timezone.now()
                )
                
                messages.success(request, f'Deposit of ${deposit.amount} rejected for {deposit.user.username}')
                
        except Exception as e:
            messages.error(request, f'Error processing deposit: {str(e)}')
        
        return redirect('admin_deposits')
    
    # Get all deposits with related data
    deposits = DepositRequest.objects.select_related(
        'user', 'cryptocurrency', 'investment_tier', 'processed_by'
    ).order_by('-created_at')
    
    # Calculate statistics
    today = timezone.now().date()
    
    # Today's statistics
    approved_today = DepositRequest.objects.filter(
        processed_at__date=today,
        status='APPROVED'
    ).aggregate(
        count=models.Count('id'),
        amount=models.Sum('amount')
    )
    
    rejected_today = DepositRequest.objects.filter(
        processed_at__date=today,
        status='REJECTED'
    ).aggregate(
        count=models.Count('id'),
        amount=models.Sum('amount')
    )
    
    # Total statistics
    total_deposits = DepositRequest.objects.aggregate(
        count=models.Count('id'),
        amount=models.Sum('amount')
    )
    
    # Pending deposits total
    pending_deposits = DepositRequest.objects.filter(status='PENDING')
    total_pending = pending_deposits.aggregate(amount=models.Sum('amount'))['amount'] or 0
    
    context = {
        'deposits': deposits,
        'total_pending': total_pending,
        'approved_today_count': approved_today['count'] or 0,
        'approved_today_amount': approved_today['amount'] or 0,
        'rejected_today_count': rejected_today['count'] or 0,
        'rejected_today_amount': rejected_today['amount'] or 0,
        'total_deposits_count': total_deposits['count'] or 0,
        'total_deposits_amount': total_deposits['amount'] or 0,
    }
    
    return render(request, 'admins/deposits.html', context)



@user_passes_test(is_admin)
def admin_investments(request):
    """Manage user investments and add profits"""
    if request.method == 'POST':
        investment_id = request.POST.get('investment_id')
        action = request.POST.get('action')
        
        try:
            investment = get_object_or_404(Investment, id=investment_id)
            
            # Replace the profit addition section in admin_investments with this:

            if action == 'add_profit':
                profit_amount = Decimal(request.POST.get('profit_amount', '0'))
                
                if profit_amount > 0:
                    # Add profit to investment
                    investment.profit_earned += profit_amount
                    investment.save()
                    
                    # Create profit transaction record
                    Transaction.objects.create(
                        user=investment.user,
                        transaction_type='PROFIT',
                        amount=profit_amount,
                        status='COMPLETED',
                        investment_tier=investment.tier,
                        notes=f'Profit added by admin for {investment.tier.name} investment'
                    )
                    
                    # Update user balances
                    investment.user.update_balances()
                    
                    messages.success(request, f'Added ${profit_amount} profit to {investment.user.username}\'s investment')
                else:
                    messages.error(request, 'Please enter a valid profit amount')
                
            elif action == 'complete':
                investment.is_completed = True
                investment.save()
                messages.success(request, f'Investment marked as completed for {investment.user.username}')
                
        except ValueError:
            messages.error(request, 'Invalid profit amount entered')
        except Exception as e:
            messages.error(request, f'Error processing investment: {str(e)}')
        
        return redirect('admin_investments')
    
    # GET request - display investments with statistics
    investments = Investment.objects.select_related('user', 'tier').order_by('-start_date')
    
    # Calculate statistics using proper aggregation
    from django.db.models import Count, Sum
    
    stats = Investment.objects.aggregate(
        total_invested=Sum('amount') or Decimal('0'),
        total_profits=Sum('profit_earned') or Decimal('0'),
        active_count=Count('id', filter=Q(is_completed=False)),
        completed_count=Count('id', filter=Q(is_completed=True))
    )
    
    context = {
        'investments': investments,
        'total_invested': stats['total_invested'],
        'total_profits': stats['total_profits'], 
        'active_count': stats['active_count'],
        'completed_count': stats['completed_count'],
    }
    
    return render(request, 'admins/investments.html', context)

@user_passes_test(is_admin)
def admin_settings(request):
    """Admin settings for wallet addresses"""
    
    # Define the cryptocurrencies we need
    crypto_data = {
        'BTC': {'name': 'Bitcoin', 'symbol': 'BTC'},
        'ETH': {'name': 'Ethereum', 'symbol': 'ETH'},
        'TON': {'name': 'Toncoin', 'symbol': 'TON'},
        'SOL': {'name': 'Solana', 'symbol': 'SOL'},
    }
    
    if request.method == 'POST':
        try:
            # Get or create cryptocurrency records
            bitcoin, created = CryptoCurrency.objects.get_or_create(
                symbol='BTC',
                defaults={'name': 'Bitcoin', 'wallet_address': '', 'is_active': True}
            )
            ethereum, created = CryptoCurrency.objects.get_or_create(
                symbol='ETH',
                defaults={'name': 'Ethereum', 'wallet_address': '', 'is_active': True}
            )
            toncoin, created = CryptoCurrency.objects.get_or_create(
                symbol='TON',
                defaults={'name': 'Toncoin', 'wallet_address': '', 'is_active': True}
            )
            solana, created = CryptoCurrency.objects.get_or_create(
                symbol='SOL',
                defaults={'name': 'Solana', 'wallet_address': '', 'is_active': True}
            )
            
            # Update wallet addresses
            btc_wallet = request.POST.get('btc_wallet', '').strip()
            eth_wallet = request.POST.get('eth_wallet', '').strip()
            ton_wallet = request.POST.get('ton_wallet', '').strip()
            sol_wallet = request.POST.get('sol_wallet', '').strip()
            
            # Only update if new value is provided
            if btc_wallet:
                bitcoin.wallet_address = btc_wallet
                bitcoin.save()
            
            if eth_wallet:
                ethereum.wallet_address = eth_wallet
                ethereum.save()
            
            if ton_wallet:
                toncoin.wallet_address = ton_wallet
                toncoin.save()
            
            if sol_wallet:
                solana.wallet_address = sol_wallet
                solana.save()
            
            messages.success(request, 'Wallet addresses updated successfully!')
            
        except Exception as e:
            messages.error(request, f'Error updating settings: {str(e)}')
        
        return redirect('admin_settings')
    
    # Get current wallet addresses
    try:
        # Get or create cryptocurrencies
        cryptocurrencies = {}
        for symbol, data in crypto_data.items():
            crypto, created = CryptoCurrency.objects.get_or_create(
                symbol=symbol,
                defaults={
                    'name': data['name'],
                    'wallet_address': '',
                    'is_active': True
                }
            )
            cryptocurrencies[data['name'].lower()] = crypto
        
    except Exception as e:
        cryptocurrencies = {}
        messages.error(request, f'Error loading cryptocurrency data: {str(e)}')
    
    context = {
        'cryptocurrencies': cryptocurrencies,
    }
    return render(request, 'admins/settings.html', context)



@user_passes_test(is_admin)
def admin_withdrawals(request):
    """Manage withdrawal requests"""
    if request.method == 'POST':
        withdrawal_id = request.POST.get('withdrawal_id')
        action = request.POST.get('action')
        
        try:
            withdrawal = get_object_or_404(WithdrawalRequest, id=withdrawal_id)
           # Replace the withdrawal approval section with this:

            if action == 'approve':
                # Update withdrawal status
                withdrawal.status = 'APPROVED'
                withdrawal.processed_at = timezone.now()
                withdrawal.processed_by = request.user
                withdrawal.save()
                
                # Update transaction status
                Transaction.objects.filter(
                    user=withdrawal.user,
                    transaction_type='WITHDRAWAL',
                    amount=withdrawal.amount,
                    status='PENDING'
                ).update(
                    status='APPROVED',
                    processed_at=timezone.now()
                )
                
                # Update user balances
                withdrawal.user.update_balances()
                
                messages.success(request, f'Withdrawal of ${withdrawal.amount} approved for {withdrawal.user.username}')
                
            elif action == 'reject':
                # Update withdrawal status
                withdrawal.status = 'REJECTED'
                withdrawal.processed_at = timezone.now()
                withdrawal.processed_by = request.user
                withdrawal.save()
                
                # Update transaction status
                Transaction.objects.filter(
                    user=withdrawal.user,
                    transaction_type='WITHDRAWAL',
                    amount=withdrawal.amount,
                    status='PENDING'
                ).update(
                    status='REJECTED',
                    processed_at=timezone.now()
                )
                
                # Since withdrawal amount was deducted when request was made, 
                # we need to add it back for rejected withdrawals
                # But first remove the pending withdrawal transaction effect by updating balances
                withdrawal.user.update_balances()
                
                messages.success(request, f'Withdrawal of ${withdrawal.amount} rejected for {withdrawal.user.username}')                
        except Exception as e:
            messages.error(request, f'Error processing withdrawal: {str(e)}')
        
        return redirect('admin_withdrawals')
    
    # Get all withdrawals with statistics
    withdrawals = WithdrawalRequest.objects.select_related(
        'user', 'cryptocurrency', 'processed_by'
    ).order_by('-created_at')
    
    # Calculate statistics
    today = timezone.now().date()
    from django.db.models import Count, Sum
    
    stats = WithdrawalRequest.objects.aggregate(
        total_pending=Sum('amount', filter=Q(status='PENDING')) or Decimal('0'),
        approved_today=Count('id', filter=Q(processed_at__date=today, status='APPROVED')),
        rejected_today=Count('id', filter=Q(processed_at__date=today, status='REJECTED')),
        total_count=Count('id')
    )
    
    context = {
        'withdrawals': withdrawals,
        'total_pending': stats['total_pending'],
        'approved_today': stats['approved_today'],
        'rejected_today': stats['rejected_today'],
        'total_count': stats['total_count'],
    }
    
    return render(request, 'admins/withdrawals.html', context)


# Add this to your views.py file

# Replace your admin_users view with this updated version

@user_passes_test(is_admin)
def admin_users(request):
    """Manage all users - view and delete with proper balance calculation"""
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        action = request.POST.get('action')
        
        try:
            user = get_object_or_404(User, id=user_id)
            
            if action == 'delete':
                # Don't allow deletion of superusers or staff
                if user.is_superuser or user.is_staff:
                    messages.error(request, 'Cannot delete admin users')
                else:
                    username = user.username
                    user.delete()
                    messages.success(request, f'User {username} deleted successfully')
                    
        except Exception as e:
            messages.error(request, f'Error processing request: {str(e)}')
        
        return redirect('admin_users')
    
    # Get all non-admin users with calculated balances
    users = User.objects.filter(is_staff=False).order_by('-date_joined')
    
    # Calculate proper balance for each user
    for user in users:
        # Get total approved deposits
        approved_deposits = user.transactions.filter(
            transaction_type='DEPOSIT',
            status='APPROVED'
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        # Get total profits
        total_profits = user.transactions.filter(
            transaction_type='PROFIT',
            status='COMPLETED'
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        # Get total approved withdrawals
        approved_withdrawals = user.transactions.filter(
            transaction_type='WITHDRAWAL',
            status='APPROVED'
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        # Calculate actual balance
        calculated_balance = approved_deposits + total_profits - approved_withdrawals
        
        # Update the balance if it's different
        if user.balance != calculated_balance:
            user.balance = calculated_balance
            user.save()
        
        # Store calculated balance for display
        user.calculated_balance = calculated_balance
    
    # Calculate user statistics
    total_users = users.count()
    active_users = users.filter(is_active=True).count()
    
    context = {
        'users': users,
        'total_users': total_users,
        'active_users': active_users,
    }
    
    return render(request, 'admins/users.html', context)

@login_required
def investments(request):
    """View user's investments with profit tracking"""
    user_investments = Investment.objects.filter(user=request.user).select_related('tier')
    
    # Calculate profit percentages
    for investment in user_investments:
        if investment.amount > 0:
            investment.profit_percentage = (investment.profit_earned / investment.amount) * 100
        else:
            investment.profit_percentage = 0
    
    context = {
        'investments': user_investments,
    }
    return render(request, 'invest/investments.html', context)





def forgot_password(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        
        try:
            # Check if user exists
            user = User.objects.get(email=email)
            
            # Generate password reset token
            from django.contrib.auth.tokens import default_token_generator
            from django.utils.http import urlsafe_base64_encode
            from django.utils.encoding import force_bytes
            from django.template.loader import render_to_string
            from django.core.mail import send_mail
            from django.conf import settings
            
            # Generate token and uid
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            
            # Create reset link (you'll need to add this URL pattern)
            reset_link = request.build_absolute_uri(f'/reset-password/{uid}/{token}/')
            
            # Email content
            subject = 'Password Reset - Ethical Investment Platform'
            message = f"""
            Hello {user.first_name or user.username},
            
            You requested a password reset for your Ethical Investment Platform account.
            
            Click the link below to reset your password:
            {reset_link}
            
            This link will expire in 24 hours.
            
            If you didn't request this reset, please ignore this email.
            
            Best regards,
            Ethical Investment Team
            """
            
            # Send email
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else 'noreply@ethical.com',
                [email],
                fail_silently=False,
            )
            
            return JsonResponse({'success': True})
            
        except User.DoesNotExist:
            # Don't reveal if email exists or not for security
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': 'Failed to send reset email'})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


def reset_password(request, uidb64, token):
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.http import urlsafe_base64_decode
    from django.utils.encoding import force_str
    
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    
    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            new_password = request.POST.get('new_password')
            confirm_password = request.POST.get('confirm_password')
            
            if new_password != confirm_password:
                messages.error(request, 'Passwords do not match')
                return render(request, 'landing/reset_password.html', {'valid_link': True})
            
            if len(new_password) < 6:
                messages.error(request, 'Password must be at least 6 characters long')
                return render(request, 'landing/reset_password.html', {'valid_link': True})
            
            # Set new password
            user.set_password(new_password)
            user.save()
            
            messages.success(request, 'Password reset successful! You can now login with your new password.')
            return redirect('signin')
        
        return render(request, 'landing/reset_password.html', {'valid_link': True})
    else:
        return render(request, 'landing/reset_password.html', {'valid_link': False})