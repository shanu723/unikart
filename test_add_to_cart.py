import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'unikart.settings')
django.setup()

from store.models import *
from django.contrib.auth.models import User
from django.test import Client

# Find a user
user = User.objects.first()
print(f"Testing with user: {user.username}")

# Find an available product and variation
variation = Variation.objects.filter(status=True, stock__gt=0).first()
if variation:
    product = variation.product
    print(f"Testing Add to Cart for Product: {product.name}, Size: {variation.size}")

    client = Client()
    client.force_login(user)

    response = client.post(f'/add_to_cart/{product.id}', {'size': variation.size})
    print(f"Add to Cart Response Status: {response.status_code}")
    if response.status_code == 302:
        print(f"Redirected to: {response.url}")

    # Check if added to cart
    cart_item = CartItem.objects.filter(user=user, product=product).first()
    if cart_item:
        print(f"SUCCESS: Cart Item created! Quantity: {cart_item.quantity}")
    else:
        print("FAILED: Cart Item not created!")
else:
    print("No available variation found!")
