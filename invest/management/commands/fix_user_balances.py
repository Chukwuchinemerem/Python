# Create this file in: your_app/management/commands/fix_user_balances.py
# Make sure to create the directories: management/ and management/commands/
# Also create __init__.py files in both directories

from django.core.management.base import BaseCommand
from django.db.models import Sum
from decimal import Decimal
from invest.models import User  # Replace 'your_app' with your actual app name

class Command(BaseCommand):
    help = 'Fix user balances by recalculating from transactions'

    def handle(self, *args, **options):
        users = User.objects.filter(is_staff=False)
        updated_count = 0
        
        for user in users:
            # Calculate correct balance
            approved_deposits = user.transactions.filter(
                transaction_type='DEPOSIT',
                status='APPROVED'
            ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
            
            total_profits = user.transactions.filter(
                transaction_type='PROFIT',
                status='COMPLETED'
            ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
            
            referral_bonuses = user.transactions.filter(
                transaction_type='REFERRAL',
                status='COMPLETED'
            ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
            
            approved_withdrawals = user.transactions.filter(
                transaction_type='WITHDRAWAL',
                status='APPROVED'
            ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
            
            # Calculate new balance
            new_balance = approved_deposits + total_profits + referral_bonuses - approved_withdrawals
            
            # Update if different
            if user.balance != new_balance:
                old_balance = user.balance
                user.balance = new_balance
                user.total_profit = total_profits + referral_bonuses
                user.save()
                
                self.stdout.write(
                    f"Updated {user.username}: ${old_balance} -> ${new_balance}"
                )
                updated_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully updated {updated_count} user balances')
        )