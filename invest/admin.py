from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db.models import Sum
from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone
from .models import (
    User, InvestmentTier, CryptoCurrency, Investment, 
    Transaction, DepositRequest, WithdrawalRequest, CryptoPrice
)

# Custom User Admin
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        'username', 'email', 'first_name', 'last_name', 
        'balance', 'total_deposited', 'total_profit', 
        'is_verified', 'date_joined'
    )
    list_filter = ('is_verified', 'country', 'date_joined', 'is_staff')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'referral_code')
    readonly_fields = ('date_joined', 'last_login', 'referral_code')
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Investment Platform Info', {
            'fields': (
                'phone', 'country', 'profile_picture', 
                'balance', 'total_deposited', 'total_withdrawn', 'total_profit',
                'referral_code', 'referred_by', 'is_verified'
            )
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('referred_by')

# Investment Tier Admin
@admin.register(InvestmentTier)
class InvestmentTierAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'roi_percentage', 'duration_hours', 
        'min_investment', 'max_investment', 'referral_bonus', 'is_active'
    )
    list_filter = ('is_active', 'name')
    search_fields = ('name',)
    list_editable = ('is_active', 'roi_percentage', 'referral_bonus')

# Cryptocurrency Admin
@admin.register(CryptoCurrency)
class CryptoCurrencyAdmin(admin.ModelAdmin):
    list_display = ('name', 'symbol', 'wallet_address', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'symbol')
    list_editable = ('is_active',)

# Investment Admin
@admin.register(Investment)
class InvestmentAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'tier', 'amount', 'start_date', 
        'end_date', 'is_completed', 'profit_earned'
    )
    list_filter = ('tier', 'is_completed', 'start_date')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('start_date',)
    date_hierarchy = 'start_date'

# Transaction Admin
@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'transaction_type', 'amount', 'status', 
        'cryptocurrency', 'created_at', 'processed_at'
    )
    list_filter = ('transaction_type', 'status', 'created_at', 'cryptocurrency')
    search_fields = ('user__username', 'user__email', 'transaction_id')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'
    
    actions = ['approve_transactions', 'reject_transactions']
    
    def approve_transactions(self, request, queryset):
        updated = queryset.filter(status='PENDING').update(
            status='APPROVED',
            processed_at=timezone.now(),
            processed_by=request.user
        )
        messages.success(request, f'{updated} transactions approved successfully.')
    approve_transactions.short_description = "Approve selected transactions"
    
    def reject_transactions(self, request, queryset):
        updated = queryset.filter(status='PENDING').update(
            status='REJECTED',
            processed_at=timezone.now(),
            processed_by=request.user
        )
        messages.success(request, f'{updated} transactions rejected successfully.')
    reject_transactions.short_description = "Reject selected transactions"

# Deposit Request Admin
@admin.register(DepositRequest)
class DepositRequestAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'amount', 'cryptocurrency', 'investment_tier',
        'status', 'created_at', 'processed_at', 'action_buttons'
    )
    list_filter = ('status', 'cryptocurrency', 'investment_tier', 'created_at')
    search_fields = ('user__username', 'user__email', 'transaction_id')
    readonly_fields = ('created_at', 'wallet_address_used')
    date_hierarchy = 'created_at'
    
    actions = ['approve_deposits', 'reject_deposits']
    
    def action_buttons(self, obj):
        if obj.status == 'PENDING':
            approve_url = reverse('admin:approve_deposit', args=[obj.pk])
            reject_url = reverse('admin:reject_deposit', args=[obj.pk])
            return format_html(
                '<a class="button" href="{}">Approve</a>&nbsp;'
                '<a class="button" href="{}">Reject</a>',
                approve_url, reject_url
            )
        return format_html('<span style="color: {};">{}</span>', 
                          'green' if obj.status == 'APPROVED' else 'red', 
                          obj.status)
    action_buttons.short_description = 'Actions'
    action_buttons.allow_tags = True
    
    def approve_deposits(self, request, queryset):
        from decimal import Decimal
        for deposit in queryset.filter(status='PENDING'):
            # Update user balance and total deposited
            user = deposit.user
            user.balance += deposit.amount
            user.total_deposited += deposit.amount
            user.save()
            
            # Create investment
            Investment.objects.create(
                user=user,
                tier=deposit.investment_tier,
                amount=deposit.amount
            )
            
            # Update deposit status
            deposit.status = 'APPROVED'
            deposit.processed_at = timezone.now()
            deposit.processed_by = request.user
            deposit.save()
            
            # Update related transaction
            Transaction.objects.filter(
                user=user,
                transaction_type='DEPOSIT',
                amount=deposit.amount,
                status='PENDING'
            ).update(
                status='APPROVED',
                processed_at=timezone.now(),
                processed_by=request.user
            )
        
        messages.success(request, f'{queryset.count()} deposits approved successfully.')
    approve_deposits.short_description = "Approve selected deposits"
    
    def reject_deposits(self, request, queryset):
        for deposit in queryset.filter(status='PENDING'):
            deposit.status = 'REJECTED'
            deposit.processed_at = timezone.now()
            deposit.processed_by = request.user
            deposit.save()
            
            # Update related transaction
            Transaction.objects.filter(
                user=deposit.user,
                transaction_type='DEPOSIT',
                amount=deposit.amount,
                status='PENDING'
            ).update(
                status='REJECTED',
                processed_at=timezone.now(),
                processed_by=request.user
            )
        
        messages.success(request, f'{queryset.count()} deposits rejected successfully.')
    reject_deposits.short_description = "Reject selected deposits"

# Withdrawal Request Admin
@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'amount', 'cryptocurrency', 'wallet_address',
        'status', 'created_at', 'processed_at', 'action_buttons'
    )
    list_filter = ('status', 'cryptocurrency', 'created_at')
    search_fields = ('user__username', 'user__email', 'wallet_address')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'
    
    actions = ['approve_withdrawals', 'reject_withdrawals']
    
    def action_buttons(self, obj):
        if obj.status == 'PENDING':
            approve_url = reverse('admin:approve_withdrawal', args=[obj.pk])
            reject_url = reverse('admin:reject_withdrawal', args=[obj.pk])
            return format_html(
                '<a class="button" href="{}">Approve</a>&nbsp;'
                '<a class="button" href="{}">Reject</a>',
                approve_url, reject_url
            )
        return format_html('<span style="color: {};">{}</span>', 
                          'green' if obj.status == 'APPROVED' else 'red', 
                          obj.status)
    action_buttons.short_description = 'Actions'
    action_buttons.allow_tags = True
    
    def approve_withdrawals(self, request, queryset):
        for withdrawal in queryset.filter(status='PENDING'):
            user = withdrawal.user
            
            # Check if user has sufficient balance
            if user.balance >= withdrawal.amount:
                # Deduct from user balance
                user.balance -= withdrawal.amount
                user.total_withdrawn += withdrawal.amount
                user.save()
                
                # Update withdrawal status
                withdrawal.status = 'APPROVED'
                withdrawal.processed_at = timezone.now()
                withdrawal.processed_by = request.user
                withdrawal.save()
                
                # Update related transaction
                Transaction.objects.filter(
                    user=user,
                    transaction_type='WITHDRAWAL',
                    amount=withdrawal.amount,
                    status='PENDING'
                ).update(
                    status='APPROVED',
                    processed_at=timezone.now(),
                    processed_by=request.user
                )
            else:
                messages.error(request, f'Insufficient balance for {user.username} withdrawal of ${withdrawal.amount}')
        
        approved_count = queryset.filter(status='APPROVED').count()
        messages.success(request, f'{approved_count} withdrawals approved successfully.')
    approve_withdrawals.short_description = "Approve selected withdrawals"
    
    def reject_withdrawals(self, request, queryset):
        for withdrawal in queryset.filter(status='PENDING'):
            withdrawal.status = 'REJECTED'
            withdrawal.processed_at = timezone.now()
            withdrawal.processed_by = request.user
            withdrawal.save()
            
            # Update related transaction
            Transaction.objects.filter(
                user=withdrawal.user,
                transaction_type='WITHDRAWAL',
                amount=withdrawal.amount,
                status='PENDING'
            ).update(
                status='REJECTED',
                processed_at=timezone.now(),
                processed_by=request.user
            )
        
        messages.success(request, f'{queryset.count()} withdrawals rejected successfully.')
    reject_withdrawals.short_description = "Reject selected withdrawals"

# Crypto Price Admin
@admin.register(CryptoPrice)
class CryptoPriceAdmin(admin.ModelAdmin):
    list_display = ('cryptocurrency', 'price_usd', 'change_24h', 'last_updated')
    list_filter = ('cryptocurrency', 'last_updated')
    readonly_fields = ('last_updated',)

# Customize admin site
admin.site.site_header = "Investment Platform Admin"
admin.site.site_title = "Investment Platform Admin"
admin.site.index_title = "Welcome to Investment Platform Administration"


# ===============================================================================================================
