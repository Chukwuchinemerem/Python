from django.db import models

# Create your models here.
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from decimal import Decimal


class User(AbstractUser):
    """Extended user model with investment platform specific fields"""
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    # profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    total_deposited = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    total_withdrawn = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    total_profit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    referral_code = models.CharField(max_length=20, unique=True, blank=True)
    referred_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)
    date_joined = models.DateTimeField(default=timezone.now)
    is_verified = models.BooleanField(default=False)
    
    def _str_(self):
        return f"{self.username} - {self.email}"
    
    @property
    def current_balance(self):
        """Calculate current balance dynamically"""
        from django.db.models import Sum
        from decimal import Decimal
        
        # Get approved deposits
        approved_deposits = self.transactions.filter(
            transaction_type='DEPOSIT', 
            status='APPROVED'
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        
        # Get all withdrawals that are PENDING or APPROVED (subtract immediately when requested)
        # Only rejected withdrawals should not be subtracted
        pending_and_approved_withdrawals = self.transactions.filter(
            transaction_type='WITHDRAWAL', 
            status__in=['PENDING', 'APPROVED']
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        
        # Get profits
        profits = self.transactions.filter(
            transaction_type='PROFIT', 
            status='COMPLETED'
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        
        # Get referral bonuses
        referral_bonuses = self.transactions.filter(
            transaction_type='REFERRAL', 
            status='COMPLETED'
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        
        # Calculate balance: deposits + profits + referrals - withdrawals(pending+approved)
        calculated_balance = approved_deposits + profits + referral_bonuses - pending_and_approved_withdrawals
        
        return calculated_balance
    
    @property
    def current_total_withdrawn(self):
        """Calculate total withdrawn dynamically - only approved withdrawals"""
        from django.db.models import Sum
        return self.transactions.filter(
            transaction_type='WITHDRAWAL', 
            status='APPROVED'
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    
    @property
    def current_total_profit(self):
        """Calculate total profit dynamically"""
        from django.db.models import Sum
        from decimal import Decimal
        
        # Get profits from investments
        profits = self.transactions.filter(
            transaction_type='PROFIT', 
            status='COMPLETED'
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        
        # Get referral bonuses
        referral_bonuses = self.transactions.filter(
            transaction_type='REFERRAL', 
            status='COMPLETED'
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        
        return profits + referral_bonuses
    
    @property
    def current_total_deposited(self):
        """Calculate total deposited dynamically"""
        from django.db.models import Sum
        from decimal import Decimal
        
        return self.transactions.filter(
            transaction_type='DEPOSIT', 
            status='APPROVED'
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    
    def update_balances(self):
        """Update stored balance fields with calculated values"""
        # Update total deposited
        self.total_deposited = self.current_total_deposited
        
        # Update total withdrawn
        self.total_withdrawn = self.current_total_withdrawn
        
        # Update total profit
        self.total_profit = self.current_total_profit
        
        # Update balance
        self.balance = self.current_balance
        
        self.save()
    
    def save(self, *args, **kwargs):
        if not self.referral_code:
            import random
            import string
            self.referral_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        
        super().save(*args, **kwargs)



class InvestmentTier(models.Model):
    """Investment tiers/packages"""
    TIER_CHOICES = [
        ('ROYAL', 'Royal'),
        ('ELITE', 'Elite'),
        ('EXECUTIVE', 'Executive'),
    ]
    
    name = models.CharField(max_length=20, choices=TIER_CHOICES, unique=True)
    roi_percentage = models.DecimalField(max_digits=5, decimal_places=2)  # 20.00 for 20%
    duration_hours = models.IntegerField(default=24)
    min_investment = models.DecimalField(max_digits=10, decimal_places=2)
    max_investment = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    referral_bonus = models.DecimalField(max_digits=5, decimal_places=2, default=5.00)
    incentive_description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    def _str_(self):
        return f"{self.name} - {self.roi_percentage}% ROI"

class CryptoCurrency(models.Model):
    """Supported cryptocurrencies"""
    name = models.CharField(max_length=50)
    symbol = models.CharField(max_length=10, unique=True)
    wallet_address = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    
    def _str_(self):
        return f"{self.name} ({self.symbol})"
    
    class Meta:
        verbose_name_plural = "Cryptocurrencies"

class Investment(models.Model):
    """User investments"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='investments')
    tier = models.ForeignKey(InvestmentTier, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField()
    is_completed = models.BooleanField(default=False)
    profit_earned = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    def _str_(self):
        return f"{self.user.username} - {self.tier.name} - ${self.amount}"
    
    def save(self, *args, **kwargs):
        if not self.end_date:
            from datetime import timedelta
            self.end_date = self.start_date + timedelta(hours=self.tier.duration_hours)
        super().save(*args, **kwargs)

class Transaction(models.Model):
    """Transaction model for deposits, withdrawals, and other transactions"""
    TRANSACTION_TYPES = [
        ('DEPOSIT', 'Deposit'),
        ('WITHDRAWAL', 'Withdrawal'),
        ('PROFIT', 'Profit'),
        ('REFERRAL', 'Referral Bonus'),
        ('INVESTMENT', 'Investment'),
    ]
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('COMPLETED', 'Completed'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    cryptocurrency = models.ForeignKey(CryptoCurrency, on_delete=models.SET_NULL, null=True, blank=True)
    wallet_address = models.CharField(max_length=200, blank=True)
    transaction_id = models.CharField(max_length=200, blank=True)
    investment_tier = models.ForeignKey(InvestmentTier, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_transactions')
    notes = models.TextField(blank=True)
    
    def _str_(self):
        return f"{self.user.username} - {self.transaction_type} - ${self.amount} - {self.status}"
    
    class Meta:
        ordering = ['-created_at']

class DepositRequest(models.Model):
    """Deposit requests from users"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='deposit_requests')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    cryptocurrency = models.ForeignKey(CryptoCurrency, on_delete=models.CASCADE)
    investment_tier = models.ForeignKey(InvestmentTier, on_delete=models.CASCADE)
    transaction_id = models.CharField(max_length=200)
    wallet_address_used = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=Transaction.STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(default=timezone.now)
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_deposits')
    
    def _str_(self):
        return f"{self.user.username} - Deposit ${self.amount} - {self.status}"
    
    class Meta:
        ordering = ['-created_at']

class WithdrawalRequest(models.Model):
    """Withdrawal requests from users"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='withdrawal_requests')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    cryptocurrency = models.ForeignKey(CryptoCurrency, on_delete=models.CASCADE)
    wallet_address = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=Transaction.STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(default=timezone.now)
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_withdrawals')
    
    def _str_(self):
        return f"{self.user.username} - Withdrawal ${self.amount} - {self.status}"
    
    class Meta:
        ordering = ['-created_at']

class CryptoPrice(models.Model):
    """Store cryptocurrency prices for display"""
    cryptocurrency = models.ForeignKey(CryptoCurrency, on_delete=models.CASCADE)
    price_usd = models.DecimalField(max_digits=15, decimal_places=2)
    change_24h = models.DecimalField(max_digits=5, decimal_places=2)
    last_updated = models.DateTimeField(default=timezone.now)
    
    def _str_(self):
        return f"{self.cryptocurrency.symbol} - ${self.price_usd}"
    
    class Meta:
        ordering = ['cryptocurrency__symbol']