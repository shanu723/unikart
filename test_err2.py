import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'unikart.settings')
django.setup()

from store.models import *
from django.contrib.auth.models import User
from django.test import Client

user = User.objects.first()

client = Client(raise_request_exception=False)
client.force_login(user)

product = Product.objects.filter(variation__isnull=False).distinct().first()
if product:
    variations = list(product.variation_set.all())
    if len(variations) >= 2:
        v1, v2 = variations[0], variations[1]
        
        # Add first variation
        response1 = client.get(f'/add_to_cart/{product.id}/{v1.size}/')
        
        # Add second variation
        response2 = client.get(f'/add_to_cart/{product.id}/{v2.size}/')
        
        if response2.status_code >= 400:
            print(f"Error {response2.status_code}")
            print(response2.content.decode()[:1000])
        else:
            print("No HTTP error on add")
            
        r3 = client.get('/cart/')
        if r3.status_code >= 400:
            print(f"Error on cart {r3.status_code}")
            print(r3.content.decode()[:1000])
        else:
            print("No error on cart page")
