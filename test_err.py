import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'unikart.settings')
django.setup()

from store.models import *
from django.contrib.auth.models import User
from django.test import Client

user = User.objects.first()
print(f"Testing with user: {user.username}")

cat, _ = Category.objects.get_or_create(name="TestCatTest", defaults={'status':True})
product, _ = Product.objects.get_or_create(name="TestProdTest", defaults={'category':cat, 'status':True})
v1, _ = Variation.objects.get_or_create(product=product, size='32', defaults={'original_price':10.0, 'stock':10, 'status':True})
v2, _ = Variation.objects.get_or_create(product=product, size='43', defaults={'original_price':20.0, 'stock':10, 'status':True})

client = Client()
client.force_login(user)

# Add first variation
response1 = client.get(f'/add_to_cart/{product.id}/{v1.size}/')
print(f"Added v1 ({v1.size}): status {response1.status_code}")

# Add second variation
try:
    response2 = client.get(f'/add_to_cart/{product.id}/{v2.size}/')
    print(f"Added v2 ({v2.size}): status {response2.status_code}")
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"ERROR on adding v2: {e}")

try:
    response3 = client.get('/cart/')
    print(f"Cart page: status {response3.status_code}")
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"ERROR on Cart Page: {e}")
    
try:
    response4 = client.post('/checkout/', {'selected_items[]': [i.id for i in CartItem.objects.filter(user=user)]})
    print(f"Checkout page: status {response4.status_code}")
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"ERROR on Checkout Page: {e}")
