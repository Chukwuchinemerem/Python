from django.core.management.base import BaseCommand
from invest.models import CryptoCurrency

class Command(BaseCommand):
    help = 'Setup initial cryptocurrencies'

    def handle(self, *args, **options):
        cryptos = [
            {'name': 'Bitcoin', 'symbol': 'BTC', 'wallet_address': 'your-btc-wallet-address'},
            {'name': 'Ethereum', 'symbol': 'ETH', 'wallet_address': 'your-eth-wallet-address'},
            {'name': 'Solana', 'symbol': 'SOL', 'wallet_address': 'your-sol-wallet-address'},
            {'name': 'Toncoin', 'symbol': 'TON', 'wallet_address': 'your-ton-wallet-address'},
        ]
        
        for crypto_data in cryptos:
            crypto, created = CryptoCurrency.objects.get_or_create(
                symbol=crypto_data['symbol'],
                defaults=crypto_data
            )
            if created:
                self.stdout.write(f'Created {crypto.name}')
            else:
                self.stdout.write(f'{crypto.name} already exists')
