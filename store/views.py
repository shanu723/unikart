import random
import razorpay
from django.conf import settings
from django.views.decorators.cache import never_cache
from django.core.paginator import Paginator
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from django.core.mail import send_mail
from django.utils import timezone
from datetime import timedelta,datetime,time
import openpyxl
import copy
from openpyxl.utils import get_column_letter
from .models import Order
from django.urls import reverse
from django.shortcuts import render,redirect
from django.contrib.auth.decorators import login_required,user_passes_test
from django.contrib.auth import authenticate, login,logout
from django.db import transaction
from django.db.models import Min,Max,Sum,Prefetch,F
from django.contrib import messages
from datetime import timedelta
from .models import *
from django.shortcuts import get_object_or_404
from django.http import JsonResponse,HttpResponse
import json
from openpyxl.styles import Font
import re
from django.utils.dateparse import parse_datetime
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.template.loader import get_template
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from .forms import CouponForm,OfferForm
from decimal import Decimal
from django.views.decorators.csrf import csrf_exempt
from django.db.models.functions import TruncDate
from store.utils import get_best_price,generate_daily_sales_report
from xhtml2pdf import pisa
from reportlab.pdfgen import canvas

def home(request):
    return render(request,'index.html') 
 
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
          
            if user.is_superuser:
                login(request, user)
                messages.success(request, "Logged in as admin.")
                return redirect('admin_dashboard') 

            
            if user.profile.is_blocked:
                messages.error(request, "Your account is blocked.")
                return redirect('login')

            
            login(request, user)
            
            messages.success(request, "Successfully logged in.")
            return redirect('user_dashboard')  
        else:
            messages.error(request, "Invalid username or password.")
            return redirect('login')
    else:
        return render(request, 'login.html')

def login_error(request):
    return render(requst,'user/login_error.html')        
@login_required
def user_dashboard(request):
    return render(request, 'user/user_dashboard.html',{'user':request.user})         

def signup_view(request):
    ref_code = request.GET.get('ref')
    if ref_code:
        try:
            UserProfile.objects.get(referral_code=ref_code)
            request.session['referral_code'] = ref_code
        except UserProfile.DoesNotExist:
            pass

    if request.method == 'POST':
        username = request.POST['username']
        email = request.POST['email']
        password = request.POST['password']
        confirm_password = request.POST['confirm_password']

        if not re.match(r'^(?=.*[A-Za-z0-9])[A-Za-z0-9]+$', username):
            messages.error(request, "Username must contain at least one letter and one number")
            return redirect('signup')
        if len(password) < 8:
            messages.error(request, "Password must be at least 8 characters")
            return redirect('signup')
        if not re.search(r'[A-Za-z]', password):
            messages.error(request, "Password must contain at least one letter")
            return redirect('signup')
        if not re.search(r'[0-9]', password):
            messages.error(request, "Password must contain at least one number")
            return redirect('signup')
        if not re.search(r'[!@#$%^&*(),.?\":{}|<>]', password):
            messages.error(request, "Password must contain at least one special character")
            return redirect('signup')
        if password != confirm_password:
            messages.error(request, 'Passwords do not match')
            return redirect('signup')
        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists")
            return redirect('signup')
        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already exists')
            return redirect('signup')

        request.session['signup_data'] = {
            'username': username,
            'password': password,
            'email': email,
        }
        code = f"{random.randint(100000, 999999)}"
        request.session['signup_otp'] = code
        request.session['signup_otp_time'] = str(timezone.now())

        send_mail(
            subject='Verification mail',
            message=f"Hi {username}, This is your OTP {code} for signup on Unikart. It will expire in 10 minutes.",
            from_email="no-reply@gmail.com",
            recipient_list=[email],
            fail_silently=False,
        )
        messages.success(request, "OTP sent successfully")
        return redirect('verify_otp', username=username)
    return render(request, 'signup.html')


def verify_otp(request, username):
    signup_data = request.session.get('signup_data')
    signup_otp = request.session.get('signup_otp')
    otp_time = request.session.get('signup_otp_time')

    if not signup_data or not signup_otp or not otp_time:
        messages.error(request, "Session expired. Please signup again.")
        return redirect('signup')
    if signup_data.get('username') != username:
        messages.error(request, "Session mismatch. Please signup again.")
        return redirect('signup')

    otp_time_obj = parse_datetime(otp_time)
    if timezone.is_naive(otp_time_obj):
        otp_time_obj = timezone.make_aware(otp_time_obj)
    if timezone.now() - otp_time_obj > timedelta(minutes=10):
        messages.error(request, "OTP expired. Please resend OTP.")
        return redirect('resend_otp', username=username)

    if request.method == 'POST':
        entered_otp = request.POST.get('otp', '').strip()
        if entered_otp == signup_otp:
            user = User.objects.create_user(
                username=signup_data['username'],
                password=signup_data['password'],
                email=signup_data['email']
            )
            user.is_active = True
            user.save()

            profile, created = UserProfile.objects.get_or_create(user=user)
            credit_wallet(user,100,"Signup bonus credited",source='signup_bonus')
            ref_code = request.session.get('referral_code')
            if ref_code:
                try:
                    referrer = UserProfile.objects.get(referral_code=ref_code)
                    if referrer.user != user:
                        profile.referred_by = referrer
                        profile.save()

                        credit_wallet(referrer.user,100,"Referral bonus credited",source='signup_bouns')
                except UserProfile.DoesNotExist:
                    pass

            user = authenticate(
                request,
                username=signup_data['username'],
                password=signup_data['password']
            )
            if user is not None:
                login(request, user)

            request.session.pop('signup_data', None)
            request.session.pop('signup_otp', None)
            request.session.pop('signup_otp_time', None)
            request.session.pop('referral_code', None)

            messages.success(request, "Account verified successfully.")
            return redirect('/profile/')
        else:
            messages.error(request, "Invalid OTP. Try again.")

    return render(request, 'verify_otp.html', {'username': username})


def resend_otp(request, username):
    signup_data = request.session.get('signup_data')
    if not signup_data or signup_data['username'] != username:
        messages.error(request, "Session expired. Please signup again")
        return redirect('signup')

    new_otp = str(random.randint(100000, 999999))
    request.session['signup_otp'] = new_otp
    request.session['signup_otp_time'] = timezone.now().isoformat()

    email = signup_data['email']
    send_mail(
        subject="Verification Mail",
        message=f"Hi {username}, This is your new OTP {new_otp} for verifying your account on Unikart",
        from_email="no-reply@gmail.com",
        recipient_list=[email],
        fail_silently=False,
    )

    messages.success(request, "A new OTP has been sent to your email")
    return redirect('verify_otp', username=username)

def credit_wallet(user,amount,description,source,order=None):
    wallet,_=Wallet.objects.get_or_create(user=user)
    wallet.balance+=amount
    wallet.save()

    WalletTransaction.objects.create(user=user,
    wallet=wallet,amount=amount,
    transaction_type='credit',source=source,
    order=order,description=description)
    Notification.objects.create(user=user,message=f"{amount} credited {description}")


def debit_wallet(user,amount,description,source,order=None):
    wallet,_=Wallet.objects.get_or_create(user=user)

    if wallet.balance >= amount:
        wallet.balance -= amount
        wallet.save()

        WalletTransaction.objects.create(
            user=user,
            wallet=wallet,
            amount=amount,
            transaction_type='debit',
            source='order_payment',
            order=order,
            description=description
        )

        return True
    return False    

@login_required
def user_list(request):
    filter_status = request.GET.get('status','all')

    if filter_status == 'blocked':
        users = User.objects.filter(profile__is_blocked = True)

    else:
        users = User.objects.all()

    return render(request,'admin_templates/user_list.html',{
        'users':users,
        'filter_status':filter_status
    })          

@login_required
def block_user(request,user_id):
    userprofile = get_object_or_404(UserProfile, user__id=user_id)
    userprofile.is_blocked=True
    userprofile.save()
    messages.success(request,'User blocked successfully')
    return redirect('user_list')
@login_required
def unblock_user(request,user_id):
    userprofile = get_object_or_404(UserProfile, user__id=user_id)
    userprofile.is_blocked=False
    userprofile.save()
    messages.success(request,'User is Unblocked successfully')
    return redirect('user_list')




@login_required
@user_passes_test(lambda u: u.is_superuser)
def admin_dashboard(request):
    generate_daily_sales_report()
    total_sales = DailySalesReport.objects.aggregate(total_revenue=Sum('total_revenue'))['total_revenue'] or 0
    total_orders = Order.objects.count()
    total_customers = User.objects.count()
    top_products = ProductSalesReport.objects.order_by('-total_quantity_sold')[:10]
    top_categories = CategorySalesReport.objects.order_by('-total_revenue')[:10]
    total_coupons_used = Order.objects.filter(discount__gt=0, status='Delivered').count()
   
    context = {
        'total_sales': total_sales,
        'total_orders': total_orders,
        'total_customers': total_customers,
        'top_products': top_products,
        'top_categories': top_categories,
        'total_coupons_used': total_coupons_used,
    }
    return render(request, 'admin_templates/admin_dashboard.html', context)
@login_required
def admin_change_password(request):
    if request.method == 'POST':
        current_password = request.POST.get('current_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')

        if not request.user.check_password(current_password):
            messages.error(request,"Currnet password is incorrect")
            return redirect('admin_change_password')
        if new_password != confirm_password:
            messages.error(request, "Passwords do not match")
            return redirect('admin_change_password')

        if len(new_password) < 8:
            messages.error(request, "Password must be at least 8 characters")
            return redirect('admin_change_password')

        request.user.set_password(new_password)
        request.user.save()

        update_session_auth_hash(request, request.user)

        messages.success(request, "Password changed successfully")
        return redirect('admin_dashboard')  

    return render(request, 'admin_templates/admin_passwrod_change.html')    

@login_required
@user_passes_test(lambda u: u.is_superuser)
def category_list(request):
    categories=Category.objects.filter(status=True)
    return render(request,'admin_templates/category.html',{'categories':categories})
@login_required    
@user_passes_test(lambda u: u.is_superuser)
def add_category(request):
    if request.method=='POST':
        name=request.POST.get('name')
        status=request.POST.get('status')=='on'

        if Category.objects.filter(name__iexact=name):
            messages.error(request,"Category Already exists")
            return redirect('add_category')

        else:
            Category.objects.create(name=name,status=status)
            messages.success(request,"Category added successfully")
            return redirect('category')

    return render(request,'admin_templates/add_category.html')      
@login_required
@user_passes_test(lambda u: u.is_superuser)
def edit_category(request,category_id):
    category=get_object_or_404(Category,id=category_id)
    if request.method=="POST":

        name=request.POST.get('name')
        status=request.POST.get('status')=='on'

        if Category.objects.filter(name__iexact=name).exclude(id=category_id).exists():
            messages.error(request,'Category name exists')
            return redirect('edit_category',category_id=category_id)
        
        category.name=name
        category.status=status
        category.save()
        messages.success(request,"Category updated successfully")
        return redirect('category')
    return render(request,'admin_templates/edit_category.html',{'category':category})    
@login_required
@user_passes_test(lambda u: u.is_superuser)
def delete_category(request,category_id):
    category=get_object_or_404(Category,id=category_id)
    category.status=False
    category.save()
    messages.success(request,"Category deleted successfully")
    return redirect('category')



@transaction.atomic
def product_list(request): 
    products = Product.objects.all().order_by('-id')

    search_product = request.GET.get('q','')
    if search_product:
        products = products.filter(name__icontains=search_product)
    paginator=Paginator(products,10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'admin_templates/products.html', {
    'page_obj':page_obj,
    'search_product':search_product})



@login_required
@user_passes_test(lambda u: u.is_superuser)
def add_product(request):
    categories= Category.objects.all()

    if request.method== 'POST':

        try:
            product_name = request.POST.get('name')
            brand = request.POST.get('brand')

            description = request.POST.get('description')

            if not product_name:
                messages.error(request,"Product name is required")
                return redirect('add_product')

            if not re.search(r'[A-Za-z0-9]',product_name):
                messages.error(request,"Product name must contains letters")
                return redirect('add_product')

            if not brand:
                messages.error(request,"Brand is required")
                return redirect('add_product')

            if not re.search (r'[A-Za-z0-9]',brand):
                messages.error(request,"Brand must containes letters")
                return redirect('add_product')

            if not description:
                messages.error(request,'Description is required')
                return redirect('add_product')

            if not re.search(r'[A-Za-z0-9]',description):
                messages.error(request,"Description must containes letters")        
                return redirect('add_product')
            status = 'status' in request.POST
            category_id = request.POST.get('category')
            stock_list = request.POST.getlist('stock[]')

            category = Category.objects.get(id=category_id)

            images = request.FILES.getlist('product_images[]')
            allowed_types = ['image/jpeg','image/png','image/webp']
            max_size_mb = 2

            if len(images)<3:
                messages.error(request,'Please upload at least three images')
                return redirect('add_product')

            for image in images:
                if image.content_type not in allowed_types:
                    messages.error(request,f'{image.name} is not allwoed ')   
                    return redirect('add_product')
                if image.size>max_size_mb * 1024*1024:
                    messages.error(request,f'{image.name} exceeds {max_size_mb}')
                    return redirect('add_product')

            product = Product.objects.create(
                name = product_name,
                brand = brand,
                description = description,
                status = status,
                category = category        
                )      

            size_list = request.POST.getlist('size[]')
            price_list = request.POST.getlist('original_price[]') 
            variation_status = request.POST.getlist('variation_status[]')

            for i in range(len(size_list)):
                price = float(price_list[i]) if i<len(price_list) else 0
                stock = int(stock_list[i]) if i <len(stock_list) else 0

                if price <= 0:
                    messages.error(request,f"Variation {size_list[i]} has invalid price")
                    product.delete()
                    return redirect('add_product')

                if stock <0:
                    messages.error(request,f'Variation {size_list[i]} has invalid stock number')
                    product.delete()
                    return redirect('add_product')    

                is_active = variation_status[i] == 'on' if i< len(variation_status) else False 

                Variation.objects.create(
                    product = product,
                    size = size_list[i],
                    original_price = price,
                    stock = stock,
                    status = is_active
                )

            keys = request.POST.getlist('highlight_keys[]')
            values = request.POST.getlist('highlight_values[]')

            for k,v in zip(keys,values):
                if k.strip() and v.strip():
                    Highlight.objects.create(product=product,key=k.strip(),value=v.strip())

            primary_index = int(request.POST.get('primary_image_index',0))
            for idx,image in enumerate(images):
                    
                ProductImages.objects.create(
                        product=product,
                        product_image=image,
                        is_primary=(idx==primary_index)
                    )     

            messages.success(request,'Product added successfully!')
            return redirect('products')

        except Exception as e:
            print(e)
            messages.error(request,'f"Something went wrong:{e}')
            return redirect('add_product')

    return render(request,'admin_templates/add_product.html',{'categories':categories})                   





@login_required
@user_passes_test(lambda u: u.is_superuser)
def edit_product(request,product_id):
    product=get_object_or_404(Product,id=product_id)
    categories=Category.objects.all()

    if request.method =='POST':
        try:
            product_name=request.POST.get('name','').strip()
            brand=request.POST.get('brand','').strip()
            description=request.POST.get('description','').strip()
            existing_variations = list(product.variation_set.all())
            existing_highlights = list(product.highlights.all())
            images = request.FILES.getlist('product_images[]')

            if not product_name:
                messages.error(request,"Product name is required")
                return redirect('add_product')

            if not re.search(r'[A-Za-z0-9]',product_name):
                messages.error(request,"Product name must contains letters")
                return render(request, 'admin_templates/edit_product.html', {
                    'product': product,
                    'existing_variations': existing_variations,
                })
            if not brand:
                messages.error(request,'Brand name is requied')
                return redirect('add_product')

            if not re.search(r'[A-Za-z0-9]',brand):
                messages.error(request,'Brand name must contains letters')
                return redirect('add_product')

            if not description:
                messages.error(request,'Description is required')
                return redirect('add_product')

            if not re.search(r'[A-Za-z0-9]',description):
                messages.error(request,'DEscription must contain letters')
                return redirect('add_product')     

            product.name = product_name
            product.brand = brand
            product.description = description

            
            product.status=request.POST.get('status')=='1'
            category_id=request.POST.get('category')
            product.category=Category.objects.get(id=category_id)
            product.save()

            size_list=request.POST.getlist('size[]')
            price_list=request.POST.getlist('original_price[]')
            stock_list = request.POST.getlist('stock[]')
            variation_status = request.POST.getlist('variation_status[]')
         

            for i in range(len(size_list)):        

                size = size_list[i]

                price = float(price_list[i]) if i < len(price_list) and price_list[i] else 0

                stock = int(stock_list[i]) if i < len(stock_list) and stock_list[i] else 0

                is_active = i < len(variation_status) and variation_status[i] == 'on'  
            
                if price <= 0:
                    messages.error(request,f"Invalid price for size {size}")
                    return redirect('edit_product',product_id=product.id)

                if stock <0:
                    messages.error(request,f"Invalid stock for size {size}")
                    return redirect('edit_product',product_id=product.id)

                if i< len(existing_variations):
                    variation = existing_variations[i]  
                    variation.size = size
                    variation.original_price=price
                    variation.stock=stock
                    variation.status = is_active
                    variation.save()

                else:
                    Variation.objects.create(
                        product=product,
                        size=size,
                        original_price=price,
                        stock=stock,
                        status=is_active
                    )          
              
          
        
            keys = request.POST.getlist('highlight_keys[]')
            values = request.POST.getlist('highlight_values[]')
          
           
            for i in range(len(keys)):
                key = keys[i].strip()
                value = values[i].strip() 

                if not key or not value:
                    continue

                if i < len(existing_highlights):

                    highlight = existing_highlights[i]
                    highlight.keys = key
                    highlight.value = value
                    highlight.save()

                else:
                    Highlight.objects.create(
                        product=product,
                        key=key,
                        value=value
                    )         

            new_images = request.FILES.getlist('images[]')

            deleted_images = request.POST.get('deleted_images','')
            deleted_ids=[]
            if deleted_images:
                deleted_ids = deleted_images.split(',')
                ProductImages.objects.filter(id__in = deleted_ids,product=product).delete()
            remaining_existing_count =product.productimages.exclude(id__in=deleted_ids).count()
            total_images = remaining_existing_count+len(new_images)

            if total_images < 3:
                messages.error(request,"Minimum 3 images are required")
                return redirect('edit_product',product_id=product.id)

            if images:
                
                allowed_types = ['image/jpeg','image/png','image/webp']
                max_size = 2 * 1024 *1024

                for image in images:

                    if image.content_type not in allowed_types:
                        messages.error(request,f"{image.name} invalid format")
                        return redirect('edit_product',product_id=product.id)

                    if image.size > max_size:
                        messages.error(request,f"{image.name} exceeds 2MB")
                        return redirect('edit_product',product_id=product.id)
                for image in images:
                    ProductImages.objects.create(
                        product=product,
                        product_image = image,
                        is_primary= False
                    )     

                primary_id = request.POST.get('primary_image_id')

                if primary_id:
                    product.productimages.update(is_primary=False)
                    ProductImages.objects.filter(id = primary_id,product=product).update(is_primary=True)     

            messages.success(request, 'Product updated successfully!')
            return redirect('products')

        except Exception as e:
            print(e)
            messages.error(request, f"Something went wrong: {e}")
            return redirect('edit_product', product_id=product.id)

    variations = product.variation_set.all()
    highlights = product.highlights.all()
    images = product.productimages.all()

    context = {
        'product': product,
        'categories': categories,
        'variations': variations,
        'highlights': highlights,
        'images': images,
    }
    return render(request, 'admin_templates/edit_product.html', context)

@never_cache
def shop(request):
    is_authenticated = request.user.is_authenticated
    sort = request.GET.get('sort','newest')
    query = request.GET.get('q')

    categories = Category.objects.filter(status=True)
    brands = Product.objects.filter(status=True).exclude(brand__isnull=True).exclude(brand='').values_list('brand', flat=True).distinct()
    selected_categories = request.GET.getlist('category')
    selected_brands = request.GET.getlist('brand')

    products = Product.objects.filter(status=True)\
        .annotate(min_var_price=Min('variation__original_price'))\
        .prefetch_related(
            Prefetch(
                'productimages',
                queryset=ProductImages.objects.filter(is_primary=True),
                to_attr='primary_image_obj'
            )
        )

    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    if min_price and max_price:
        min_price = int(min_price)
        max_price = int(max_price)
        products = products.filter(min_var_price__gte=min_price, min_var_price__lte=max_price)

    if selected_categories:
        products = products.filter(category__id__in=selected_categories)

    if selected_brands:
        products = products.filter(brand__in=[b.strip() for b in selected_brands])

    if query:
        products = products.filter(name__icontains=query)

    if sort == 'low_to_high':
        products = products.annotate(min_price=Min('variation__original_price')).order_by('min_price')
    elif sort == 'high_to_low':
        products = products.annotate(min_price=Min('variation__original_price')).order_by('-min_price')
    elif sort == 'a_to_z':
        products = products.order_by('name')
    elif sort == 'z_to_a':
        products = products.order_by('-name')
    else:
        products = products.order_by('-created_at')

    paginator = Paginator(products, 9)
    page_number = request.GET.get('page')
    products = paginator.get_page(page_number)

    wishlist_product_ids = []
    if is_authenticated:
        wishlist_product_ids = list(Wishlist.objects.filter(user=request.user).values_list('product_id', flat=True))

    context = {
        'products': products,
        'is_authenticated': is_authenticated,
        'current_sort': sort,
        'categories': categories,
        'brands': brands,
        'selected_categories': selected_categories,
        'selected_brands': selected_brands,
        'wishlist_product_ids': wishlist_product_ids,
        'min_price': min_price,
        'max_price': max_price,
        'query': query,
    }

    return render(request, 'shop.html', context)
@login_required    
def products(request):
    products=Product.objects.all()
    return render(request,'admin_templates/products.html',{'products':products})    



@login_required    
def toggle_product_status(request,product_id):
    if request.method=='POST':
        product = get_object_or_404(Product,id=product_id)
        product.status = not product.status
        product.save()

        return JsonResponse({'status':product.status})

@login_required
def product_details(request, id):
    product = get_object_or_404(Product, id=id)
    description = product.description
    variations = product.variation_set.all()
    product_images = product.productimages.all()
    highlights = product.highlights.all()

    in_wishlist = False
    if request.user.is_authenticated:
        in_wishlist = Wishlist.objects.filter(user=request.user, product=product).exists()
    
    for variation in variations:
        variation.final_price, variation.discount_percentage = get_best_price(variation)

    if variations:
        default_variation = variations[0]
        default_final_price = default_variation.final_price
        default_discount = default_variation.discount_percentage
    else:
        default_final_price = None
        default_discount = 0

    total_stock = sum(v.stock or 0 for v in variations)

    related_products = Product.objects.filter(category=product.category).exclude(id=product.id)[:4]
    for rel in related_products:
        first_var = rel.variation_set.first()
        if first_var:
            rel.final_price, rel.discount_percentage = get_best_price(first_var)
        else:
            rel.final_price, rel.discount_percentage = None, 0

    context = {
        "product": product,
        "description":description,
        "variations": variations,
        "product_images": product_images,
        "default_final_price": default_final_price,
        "default_discount": default_discount,
        "related_products": related_products,
        "highlights": highlights,
        "total_stock": total_stock,
        "in_wishlist": in_wishlist,
    }

    return render(request, "product_details.html", context)

def contact(request):
    return render(request,'contact.html')

def about(request):
    return render(request, 'about.html')

@login_required
@user_passes_test(lambda u:u.is_superuser)
def add_offer(request):
    if request.method == 'POST':
        form = OfferForm(request.POST)
        if form.is_valid():
            offer = form.save(commit=False)

            if form.cleaned_data['offer_type'] == 'product':
                offer.category = None
            elif form.cleaned_data['offer_type'] == 'category':
                offer.product = None
            offer.save()
            messages.success(request,"Offer created successfully")
            return redirect('offers_list')
    else:
        form = OfferForm()
    categories = Category.objects.all()
    products = Product.objects.all()

    return render(request,'admin_templates/add_offer.html',{
        'form':form,
        'categories':categories,
        'products':products
    })



@login_required
@user_passes_test(lambda u: u.is_superuser)
def offers_list(request):
    offers = Offer.objects.all().order_by('-id')

    search_offer = request.GET.get('q','')
    if search_offer :
        offers = offers.filter(title__icontains=search_offer)

    paginator =Paginator(offers,10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request,'admin_templates/offers_list.html',{'offers':offers,
    'page_obj':page_obj,
    'search_offer':search_offer})

@login_required
@user_passes_test(lambda u: u.is_superuser)
def edit_offer(request, offer_id):
    offer = Offer.objects.get(pk=offer_id)

    if request.method == 'POST':
        form = OfferForm(request.POST, instance=offer)
        if form.is_valid():
            offer = form.save(commit=False)

            if offer.offer_type == 'product':
                offer.category = None
            else:
                offer.product = None

            offer.save()
            messages.success(request, "Offer updated successfully")
            return redirect('offers_list')
    else:
        form = OfferForm(instance=offer)

    categories = Category.objects.all()
    products = Product.objects.all()

    return render(request, 'admin_templates/edit_offer.html', {
        'form': form,
        'offer': offer,
        'categories': categories,
        'products': products
    })

@login_required
@user_passes_test(lambda u: u.is_superuser)
def delete_offer(request,id):
    offer_to = get_object_or_404(Offer,id=id)
    offer_to.delete()
    messages.success(request,'Offers deleted successfully.')
    return redirect('offers_list')
    return render(request,'admin_templates/admin_dashboard.html')    

@login_required(login_url='login')
def add_to_cart(request, product_id, size):
    product = get_object_or_404(Product, id=product_id)
    variation = get_object_or_404(Variation, product=product, size=size,status =True)
    
    if variation.stock <=0:
        messages.error(request,"This is out of stock")
        return redirect('product_details',product_id=product.id)
    cart_item, created = CartItem.objects.get_or_create(
        user=request.user,
        product=product,
        variation=variation,
        defaults={'quantity': 1, 'unit_price': get_best_price(variation)[0]}
    )

    if not created:
        if cart_item.quantity >= variation.stock:
            messages.error(request,"No more stock avilable")
            return redirect('cart')
        cart_item.quantity += 1
        cart_item.save()
    Wishlist.objects.filter(user=request.user,product = product).delete()
    print(product_id, size)

    messages.success(request,"Item moved to cart successfully")
    return redirect('cart')

@login_required(login_url='login')

def cart(request):
    items = CartItem.objects.filter(user=request.user)

    
    for item in items:
        try:
            variation = item.variation
            item.unit_price, _ = get_best_price(variation)  
        except Variation.DoesNotExist:
            item.unit_price = 0

        item.line_total = float(item.unit_price * item.quantity)

    context = {
        'items': items,
    }
    return render(request, 'cart.html', context)


MAX_CART_ITRM_LIMIT=5
@login_required(login_url='login')
def update_cart_item(request):
    if request.method != 'POST':
        return JsonResponse({'error':'Invalid request method'},status=400)
    try:
        data = json.loads(request.body)
        item_id =data.get('id')
        requested_quantity = max(1,int(data.get('quantity',1)))
        cart_item = get_object_or_404(CartItem,id=item_id,user=request.user)
        variation = cart_item.variation

        if requested_quantity >MAX_CART_ITRM_LIMIT:
            return JsonResponse({'error':f"Maximum {MAX_CART_ITRM_LIMIT} items allowed"},status=400)
        if requested_quantity >variation.stock:
            return JsonResponse({'error':f'Only {variation.stock} itmes avilable'},status=400)
        unit_price,_=get_best_price(variation)

        cart_item.quantity = requested_quantity
        cart_item.unit_price = unit_price
        cart_item.save()

        return JsonResponse({ 'item':{'id':cart_item.id,'quantity':cart_item.quantity,'line_total':float(unit_price*cart_item.quantity)}})
    except Exception as e:
        return JsonResponse({'error':str(e)},status=400)          


@login_required(login_url='login')
def remove_cart_item(request, item_id):
    if request.method == "POST":
        cart_item = get_object_or_404(CartItem, id=item_id, user=request.user)
        cart_item.delete()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

@login_required
@user_passes_test(lambda u: u.is_superuser)
def coupon_list(request):
    coupons = Coupon.objects.all().order_by('-id')
    return render (request,'admin_templates/coupon_list.html',{'coupons':coupons})
@login_required
@user_passes_test(lambda u: u.is_superuser)
def add_coupon(request):
    if request.method == "POST":
        form = CouponForm(request.POST)

        if form.is_valid():
            form.save()
            messages.success(request,"Coupon added successfully")
            return redirect('coupon_list')
        else:
            messages.error(request,"Please correct he error below")
    else:
        form = CouponForm()
    return render(request,'admin_templates/add_coupon.html',{'form':form})    

@login_required
@user_passes_test(lambda u: u.is_superuser)
def edit_coupon(request, id):
    coupon = get_object_or_404(Coupon, id=id)

    if request.method == "POST":
        form = CouponForm(request.POST, instance=coupon)

        if form.is_valid():
            form.save()
            messages.success(request, "Coupon updated successfully!")
            return redirect('coupon_list')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = CouponForm(instance=coupon)

    return render(request, 'admin_templates/edit_coupon.html', {
        'form': form
    })
@login_required
def delete_coupon(request,id):
    coupon = get_object_or_404(Coupon,id=id)
    coupon.active = False
    coupon.save()
    messages.success(request,"Coupon deactivated successfully")
    return redirect('coupon_list')  

@login_required(login_url='login')

def apply_coupon(request):

    if request.method == "POST":
       
        if request.POST.get('remove_coupon'):
            request.session.pop("coupon_id", None)
            request.session.pop("coupon_cart_items", None)
            messages.success(request, "Coupon removed successfully")
            buy_now_item_id = request.session.get('buy_now_item')
            if buy_now_item_id:
                return redirect(f'/checkout/?buy_now_item={buy_now_item_id}')
            return redirect('checkout')
       
        code = request.POST.get("coupon_code")
        if not code:
            messages.error(request, "Please enter a coupon code")
            return redirect('checkout')
        try:
            coupon = Coupon.objects.get(
                code__iexact=code,
                active=True,
                valid_from__lte=timezone.now()
            )
         
            if coupon.valid_to and coupon.valid_to < timezone.now():

                messages.error(request, "Coupon expired")
                return redirect('checkout')
           
            if CouponUsage.objects.filter(user=request.user, coupon=coupon).exists():

                messages.error(request, "You have already used this coupon")
                return redirect('checkout')
           
            selected_items = request.POST.getlist('selected_items[]')
        
            buy_now_item_id = request.session.get('buy_now_item')
            if buy_now_item_id:
                selected_items = [str(buy_now_item_id)]
          
            request.session['coupon_id'] = coupon.id
            request.session['coupon_cart_items'] = selected_items
            messages.success(request, f"Coupon '{coupon.code}' applied successfully")
        except Coupon.DoesNotExist:
            messages.error(request, "Invalid coupon code")
    buy_now_item_id = request.session.get('buy_now_item')
    if buy_now_item_id:
        return redirect(f'/checkout/?buy_now_item={buy_now_item_id}')
    return redirect('checkout')


@login_required
def stock_list(request):
    stock_items = Variation.objects.select_related('product').order_by('-created_at')

    search = request.GET.get('search','')
    if search:
        stock_items = stock_items.filter(product__name__icontains=search)
        
    stock_filter = request.GET.get('filter','')
    if stock_filter == 'low':
        stock_items = stock_items.filter(stock__gte=0,stock__lte=5)
    elif stock_filter == 'zero':
        stock_items = stock_items.filter(stock=0)
    paginator = Paginator(stock_items,10)
    page_number = request.GET.get('page')
    stock_items = paginator.get_page(page_number)

    context = {'stock_items':stock_items,'search':search,'filter':stock_filter} 
    return render(request,'admin_templates/stock_list.html',context)   
    

@login_required
def wishlist(request):
    return render(request,'user/wishlist.html')

@login_required(login_url='login')
def buy_now(request, product_id, size):

    product = get_object_or_404(Product, id=product_id)
    variation = get_object_or_404(Variation, product=product, size=size)

    final_price, discount = get_best_price(variation)

    cart_item = CartItem.objects.create(
        user=request.user,
        product=product,
        variation=variation,
        quantity=1,
        unit_price=final_price
    )

    request.session['buy_now_item'] = cart_item.id

    return redirect(f"/checkout/?buy_now_item={cart_item.id}")


@login_required
def profile_view(request):
    user = request.user
    addresses = Address.objects.filter(user=user)

    is_google_user = user.social_auth.filter(provider='google-oauth2').exists()

    return render(request, "user/profile.html", {
        "user": user,
        "addresses": addresses,
        "is_google_user":is_google_user,
        
        })

@login_required
def update_profile(request):
    user = request.user
    profile = user.profile
    is_google_user = user.social_auth.filter(provider='google-oauth2').exists()

    if request.method == 'POST':
        new_username = request.POST.get('username', '').strip()
        new_email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        photo = request.FILES.get('profile_photo')
        if new_username:
            new_username = new_username.strip()
            if new_username != user.username:
                if not re.match(r'^(?=.*[A-Za-z0-9])[A-Za-z0-9_]{3,20}$', new_username):
                    messages.error(request, "Username must be 3-20 chars, letters/numbers/underscore only.")
                    return redirect('profile')
                if User.objects.exclude(id=user.id).filter(username=new_username).exists():
                    messages.error(request, "Username already taken.")
                    return redirect('profile')
                user.username = new_username
        if new_email:
            new_email = new_email.strip()

            if new_email != user.email:
                if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', new_email):
                    messages.error(request, "Enter a valid email.")
                    return redirect('profile')
                if is_google_user:
                    messages.error(request, "Google users cannot change email.")
                    return redirect('profile')

                otp = str(random.randint(100000, 999999))
                request.session['update_email'] = new_email
                request.session['update_otp'] = otp
                request.session['update_otp_time'] = timezone.now().isoformat()

                send_mail(
                    subject="Email verification",
                    message=f"Your OTP is {otp}",
                    from_email="no-reply@gmail.com",
                    recipient_list=[new_email],
                )
                messages.success(request, "OTP sent to new email")
                return redirect('verify_update_otp')

        phone = request.POST.get('phone', '').strip()

        cleaned_phone = re.sub(r'\D', '', phone)

        if cleaned_phone:
            if len(cleaned_phone) != 10:
                messages.error(request, "Enter a valid 10-digit phone number.")
                return redirect('profile')
            if cleaned_phone == '0000000000':
                messages.error(request, "Phone number cannot be all zeros.")
                return redirect('profile')      

            profile.phone = cleaned_phone

        if photo:
            profile.profile_photo = photo
        user.save()
        profile.save()
        user.save()
        messages.success(request, "Profile updated successfully.")
        return redirect('profile')


@login_required
def verify_update_otp(request):
    otp = request.session.get('update_otp')
    otp_time = request.session.get('update_otp_time')
    new_email = request.session.get('update_email')

    if not otp or not new_email:
        messages.error(request, "Session expired")
        return redirect('profile')

    if request.method == 'POST':
        entered_otp = request.POST.get('otp')

        otp_time = timezone.datetime.fromisoformat(otp_time)

        if timezone.now() - otp_time > timedelta(minutes=2):
            messages.error(request, "OTP expired")
            return redirect('profile')

        if entered_otp == otp:
            request.user.email = new_email
            request.user.save()

            for k in ['update_otp', 'update_otp_time', 'update_email']:
                request.session.pop(k, None)

            messages.success(request, "Email updated successfully")
            return redirect('profile')

        else:
            messages.error(request, "Invalid OTP")

    return render(request, 'verify_update_otp.html')

@login_required
def resend_update_otp(request):
    new_email = request.session.get('update_email')
    
    if not new_email:
        messages.error(request, "Session expired. Please try updating profile again.")
        return redirect('profile')

    otp = str(random.randint(100000, 999999))
    request.session['update_otp'] = otp
    request.session['update_otp_time'] = timezone.now().isoformat()

    send_mail(
        subject="Email Verification - Resend OTP",
        message=f"Your new OTP is {otp}",
        from_email="no-reply@gmail.com",
        recipient_list=[new_email],
    )

    messages.success(request, "A new OTP has been sent to your email")
    return redirect('verify_update_otp')        


@login_required
def change_password(request):
    user = request.user
    if not user.is_authenticated:
        messages.error(request,"You need to login to change your password.")
        return render(request,'login.html')
    if not user.has_usable_password():
        messages.error(request,"Google users cannot change passswrod here.")
        return render(request,'user/user_dashboard.html')    
    if request.method == 'POST':
        form = PasswordChangeForm(user,request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request,user)
            messages.success(request,"Password changed successfully")
            return redirect('profile')
    else:
        form =PasswordChangeForm(user)
    return render(request,'user/change_password.html',{'form':form})        

@login_required    
def address_list(request):
    addresses = Address.objects.filter(user=request.user)
    
    return render(request, "address_list.html", {"addresses": addresses})

@login_required(login_url='login')
def add_address(request):
    if request.method=='POST':
        street=request.POST.get('street')
        city=request.POST.get('city')
        district=request.POST.get('district')
        state=request.POST.get('state')
        pincode=request.POST.get('pincode')
  
        is_default=request.POST.get('is_default')=='on'
        if not re.match(r'^[A-Za-z1-9\s,.\-/#]+$', street):
            messages.error(request,'Street must be atleast 5 letters')
            return redirect('profile')
        if not city.replace(" ","").isalpha():
            messages.error(request,"City should contain letters only")  
            return redirect('profile')
        if not state.replace(" ","").isalpha():
            messages.error(request,"Sate should contain only letters")
            return redirect('profile')
        if not re.match(r'^\d{6}$',pincode):          
            messages.error(request,"Pincode must be exactly 6 digits")
            return redirect('profile')
        if is_default:
            Address.objects.filter(user=request.user,is_default=True).update(is_default=False)
        Address.objects.create(
            user=request.user,
            street=street,
            city=city,
            district=district,
            state=state,
            pincode=pincode,
 
            is_default=is_default
        )    
        return redirect('profile')
    return redirect('profile')
@login_required
def edit_address(request,address_id):
    address=get_object_or_404(Address,id=address_id,user=request.user)
    if request.method=='POST':
        address.street=request.POST.get('street')  
        address.city=request.POST.get('city') 
        address.district=request.POST.get('district') 
        address.state=request.POST.get('state') 
        address.pincode=request.POST.get('pincode') 
        address.street=request.POST.get('street') 
      
        address.is_default=request.POST.get('is_default')=='on' 
        if len(address.street) < 5:
            messages.error(request, "Street must be at least 5 characters")
            return redirect('profile')
        if not address.city.replace(" ", "").isalpha():
            messages.error(request, "City should contain only letters")
            return redirect('profile')
        if not address.district.replace(" ", "").isalpha():
            messages.error(request, "District should contain only letters")
            return redirect('profile')
        if not address.state.replace(" ", "").isalpha():
            messages.error(request, "State should contain only letters")
            return redirect('profile')
        if not re.match(r'^\d{6}$', address.pincode):
            messages.error(request, "Invalid pincode")
            return redirect('profile') 

        if address.is_default:
            Address.objects.filter(user=request.user, is_default=True).exclude(id=address.id).update(is_default=False)

        address.save()
        return redirect('profile')
    return redirect('profile')    

@login_required
def remove_address(request,address_id):
    address=get_object_or_404(Address,id=address_id,user=request.user) 
    address.delete()
    return redirect('profile')   

@login_required
def set_default_address(request,address_id):
    Address.objects.filter(user=request.user,is_default=True).update(is_default=False)
    address=get_object_or_404(Address,id=address_id,user=request.user)
    address.is_default=True
    address.save()
    return redirect('profile')   

def send_email_otp(request):
    email = request.POST.get("email")
    user = request.user
    if not email:
        return JsonResponse({"success": False, "message": "Email required"})
    otp = str(random.randint(100000, 999999))
    EmailOTP.objects.filter(user=user, email=email).delete()
    EmailOTP.objects.create(
        user=user,
        email=email,
        otp=otp
    )
    request.session["pending_email"] = email
    send_mail(
        "Email Verification OTP",
        f"Your OTP is {otp}. Valid for 5 minutes.",
        "noreply@yourapp.com",
        [email]
    )
    return JsonResponse({"success": True, "message": "OTP sent successfully"})

def verify_email_otp(request):
    otp = request.POST.get("otp")
    email = request.session.get("pending_email")
    if not email:
        return JsonResponse({"success": False, "message": "Session expired"})
    try:
        record = EmailOTP.objects.get(
            user=request.user,
            email=email,
            otp=otp
        )
        if record.is_expired():
            record.delete()
            return JsonResponse({"success": False, "message": "OTP expired"})
        request.user.email = email
        request.user.save()
        record.delete()
        del request.session["pending_email"]
        return JsonResponse({"success": True, "message": "Email verified"})
    except EmailOTP.DoesNotExist:
        return JsonResponse({"success": False, "message": "Invalid OTP"})


def resend_email_otp(request):
    email = request.session.get("pending_email")
    if not email:
        return JsonResponse({"success": False, "message": "No pending email"})
    otp = str(random.randint(100000, 999999))
    EmailOTP.objects.filter(
        user=request.user,
        email=email
    ).delete()
    EmailOTP.objects.create(
        user=request.user,
        email=email,
        otp=otp
    )
    send_mail(
        "Resend Email OTP",
        f"Your new OTP is {otp}.",
        "noreply@yourapp.com",
        [email]
    )
    return JsonResponse({"success": True, "message": "OTP resent"})
   
@login_required
def wallet_view(request):
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    transaction_type = request.GET.get('type')
    transactions = WalletTransaction.objects.filter(wallet=wallet)
    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)
    transactions = transactions.order_by('-created_at')
    paginator = Paginator(transactions, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = {
        'wallet': wallet,
        'page_obj': page_obj,
        'selected_type': transaction_type
    }
    return render(request, 'user/wallet.html', context)


client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
@login_required
def add_money_to_wallet(request):
    if request.method == 'POST':
        amount_rupees = Decimal(request.POST.get('amount'))
        amount_paisa = int(amount_rupees * 100)
        wallet, created = Wallet.objects.get_or_create(user=request.user)
        razorpay_order = client.order.create({
            'amount': amount_paisa,
            'currency':'INR',
            'payment_capture':'1'
        })
        return JsonResponse({
            "razorpay_order_id": razorpay_order["id"],
            "razorpay_key_id": settings.RAZORPAY_KEY_ID,
            "amount": amount_paisa
        })
    return JsonResponse({"error":"Invalid request"},status=400)      

@csrf_exempt
def wallet_payment_success(request):
    if request.method == 'POST':
        payment_id = request.POST.get('razorpay_payment_id')
        order_id = request.POST.get('razorpay_order_id')
        amount = request.POST.get('amount')
        if payment_id and order_id and amount:
            amount_decimal = Decimal(amount)
            credit_wallet(
                user=request.user,
                amount=amount_decimal,
                description=f"Added via Razorpay | Payment ID: {payment_id}",
                source='wallet_recharge'
            )
        return redirect('wallet')
    return render(request, 'profile')    

@login_required
def admin_wallet_transactions(request):
    wallets = Wallet.objects.select_related('user').all()
    return render(request, 'admin_templates/admin_wallet_transaction.html', {'wallets': wallets})

@login_required
def admin_user_wallet(request, user_id):
    user = get_object_or_404(User, id=user_id)
    wallet = get_object_or_404(Wallet, user=user)
    transactions = WalletTransaction.objects.filter(wallet=wallet).order_by('-created_at')

    return render(request, 'admin_templates/admin_user_wallet.html', {
        'wallet_user': user,
        'wallet': wallet,
        'transactions': transactions
    })
        
@login_required  
def myorders_view(request):
    status = request.GET.get('status', 'All')
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
  
    if status == "Cancelled":
        orders = orders.filter(items__status="Cancelled").distinct()
    elif status == "Returned":
        orders = orders.filter(items__status="Returned").distinct()
    elif status == "Delivered":
        orders = orders.filter(items__status="Delivered").distinct()    
    orders = orders.order_by('-created_at')
    paginator = Paginator(orders, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'user/myorders.html', {
        'page_obj': page_obj,
        'current_status': status
    })

@login_required
def order_detail(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    payment = Payment.objects.filter(order=order).first()
    items = order.items.all()
    processed_items = []
    is_revised = False   
    for item in items:
        cancelled_qty = item.cancelled_quantity or 0
        returned_qty = item.returned_quantity or 0
        if cancelled_qty > 0 or returned_qty > 0:
            is_revised = True   
        final_qty = item.quantity - cancelled_qty - returned_qty
        item.final_quantity = final_qty
        item.final_total = item.price * final_qty
        processed_items.append(item)
    return render(request, 'user/order_details.html', {
        'order': order,
        'items': processed_items,
        'payment': payment,
        'order_status': order.status,
        'is_revised': is_revised   
    })

@login_required
def return_item(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id, order__user=request.user)
    if request.method == 'POST':
        reason = request.POST.get('reason')
        if ReturnRequest.objects.filter(item=item).exists():
            messages.warning(request, "Return already requested for this item")
            return redirect('myorders')
        ReturnRequest.objects.create(
            item=item,
            user=request.user,
            reason=reason,
            status='Pending'
        )
        item.status = "Return Requested"
        item.save()
        messages.success(
            request,
            f"Return request sent for item #{item.id}"
        )
        return redirect('myorders')
    return render(request, 'user/return_item.html', {'item': item,'order': item.order})

@login_required(login_url='login')
@never_cache
def order_confirmation(request):
    order_id = request.session.get('order_id')
    if not order_id:
        messages.error(request,"No recent order found")
        return redirect('cart')
    try:
        order = Order.objects.get(id=order_id,user=request.user)
        order_items = OrderItem.objects.filter(order=order)
    except Order.DoesNotExist:
        messages.error(request,"Order not found")
        return redirect('cart')
 
    del request.session['order_id']
    context = {
        'order':order,
        'order_items':order_items,
        'address':order.address,
    }    
    return render(request,'user/order_confirmation.html',context)

def logout_view(request):
    logout(request)
    request.session.flush()
    return render(request,'index.html')     


def login_error(request):
    messages.error(request, "There was an error during social authentication.")
    return redirect('login')


def order_list(request):
    orders=Order.objects.all().order_by("-created_at")
    paginator=Paginator(orders,10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request,'admin_templates/order_list.html',{'page_obj':page_obj})


ORDER_FLOW = {
    "Ordered": ["Pending", "Processing", "Cancelled"],  
    "Pending": ["Processing", "Shipped", "Delivered"],
    "Confirmed": ["Processing", "Shipped","Delivered","Cancelled"],
    "Processing": ["Shipped", "Delivered"],
    "Shipped": ["Delivered"],
    "Delivered": [],
    "Cancelled": [],
    "Partially Cancelled": ["Processing", "Shipped", "Delivered"], 
    "Partially Returned": ["Processing", "Shipped", "Delivered"],
}

@login_required
def cus_order_details(request, order_id):
    order = (
        Order.objects
        .select_related("user")
        .prefetch_related("items__product", "items__variation")
        .get(id=order_id)
    )
   
    unit_items = []
    for item in order.items.all():
        cancelled = item.cancelled_quantity or 0
        returned = item.returned_quantity or 0
        for i in range(item.quantity):
            unit = copy.deepcopy(item)  
            unit.cancelled = i < cancelled
            unit.returned = i < returned
            unit.allowed_status = ORDER_FLOW.get(item.status, [])
            unit.index = i
            unit_items.append(unit)
    return render(request, "admin_templates/cus_order_details.html", {
        "order": order,
        "unit_items": unit_items,
    })

@login_required
def update_item_status(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id)
    order = item.order
    if request.method == "POST":
        new_status = request.POST.get("status")
        if not new_status:
            messages.error(request, "Please select a status")
            return redirect("cus_order_details", order_id=order.id)
      
        cancelled_qty = item.cancelled_quantity or 0
        returned_qty = item.returned_quantity or 0
        remaining = item.quantity - cancelled_qty - returned_qty
        if remaining <= 0:
            messages.warning(request, "No units left to update")
            return redirect("cus_order_details", order_id=order.id)
       
        allowed_next = ORDER_FLOW.get(item.status, [])
        if new_status not in allowed_next:
            messages.error(
                request,
                f"Cannot change status from '{item.status}' to '{new_status}'"
            )
            return redirect("cus_order_details", order_id=order.id)
       
        if new_status == "Cancelled":
            item.cancelled_quantity = cancelled_qty + 1
        elif new_status == "Returned":
            item.returned_quantity = returned_qty + 1
        else:
         
            item.status = new_status
      
        if item.cancelled_quantity == item.quantity:
            item.status = "Cancelled"
        elif item.returned_quantity == item.quantity:
            item.status = "Returned"
   
        item.save()
    
        all_items = order.items.all()
        if all(i.status in ["Cancelled", "Returned"] for i in all_items):
            order.status = "Cancelled"
        elif any(i.status == "Shipped" for i in all_items):
            order.status = "Shipped"
        elif any(i.status == "Processing" for i in all_items):
            order.status = "Processing"
        elif all(i.status in ["Delivered", "Cancelled", "Returned"] for i in all_items):
            order.status = "Delivered"
        else:
            order.status = "Pending"
        order.save()
        messages.success(
            request,
            f"Item #{item.id} updated. Remaining units: {item.quantity - (item.cancelled_quantity or 0) - (item.returned_quantity or 0)}"
        )
    return redirect("cus_order_details", order_id=order.id)
      

@login_required
def add_to_wishlist(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if Wishlist.objects.filter(user=request.user, product=product).exists():
        Wishlist.objects.filter(user=request.user, product=product).delete()
        if is_ajax:
            return JsonResponse({'status': 'removed', 'message': 'Removed from wishlist'})
        messages.info(request, "Product removed from wishlist")
    else:
        Wishlist.objects.create(user=request.user, product=product)
        if is_ajax:
            return JsonResponse({'status': 'added', 'message': 'Added to wishlist'})
        messages.success(request, "Product added to wishlist")

    return redirect('wishlist')

@login_required
def wishlist(request):
    wishlist_items= Wishlist.objects.filter(user=request.user).select_related('product')
    return render(request,'user/wishlist.html',{'wishlist_items':wishlist_items})

@login_required
def remove_wishlist(request,id):
    item = get_object_or_404(Wishlist,id=id,user=request.user)
    item.delete()
    messages.success(request,"Product removed from your wishlist")
    return redirect('wishlist')


@login_required(login_url='login')
@never_cache
def check_out(request):
    user = request.user
    now = timezone.now()

    available_coupons = Coupon.objects.filter(
        active=True,
        valid_from__lte=now
    ).exclude(couponusage__user=user)

    if request.GET.get('buy_now_item'):
        buy_now_item_id = request.GET.get('buy_now_item')
        request.session['buy_now_item'] = buy_now_item_id
        selected_ids = [buy_now_item_id]

    elif request.method == "POST":
        selected_ids = request.POST.getlist('selected_items[]')
        if 'buy_now_item' in request.session:
            del request.session['buy_now_item']

    elif request.session.get('buy_now_item'):
        selected_ids = [request.session.get('buy_now_item')]

    else:
        selected_ids = list(
            CartItem.objects.filter(user=user).values_list('id', flat=True)
        )

    if not selected_ids:
        messages.error(request, "Please select at least one item to checkout.")
        return redirect('cart')

    items = CartItem.objects.filter(user=user, id__in=selected_ids)

    subtotal = sum(item.unit_price * item.quantity for item in items)
    shipping = 50 if subtotal > 500 else 0
    discount = 0
    coupon = None

    coupon_id = request.session.get('coupon_id')
    coupon_cart_items = request.session.get('coupon_cart_items', [])

    if coupon_id and set(map(str, selected_ids)) == set(coupon_cart_items):
        try:
            coupon = Coupon.objects.get(
                id=coupon_id,
                active=True,
                valid_from__lte=now
            )

            if coupon.valid_to and coupon.valid_to < now:
                raise Coupon.DoesNotExist

            discount = coupon.calculate_discount(subtotal)

            if coupon.min_purchase_amount and subtotal < coupon.min_purchase_amount:
                messages.error(request, "Minimum purchase amount not reached for this coupon.")
                discount = 0
                request.session.pop('coupon_id', None)

        except Coupon.DoesNotExist:
            discount = 0
            request.session.pop('coupon_id', None)

    total = subtotal - discount + shipping

    for item in items:
        item.line_total = item.unit_price * item.quantity

    user_addresses = Address.objects.filter(user=user)
    default_address = user_addresses.filter(is_default=True).first()
    selected_address_id = request.POST.get('selected_address') or (
        default_address.id if default_address else None
    )

    context = {
        'items': items,
        'subtotal': subtotal,
        'shipping': shipping,
        'discount': discount,
        'total': total,
        'coupon': coupon,
        'available_coupons': available_coupons,
        'user_addresses': user_addresses,
        'selected_addresses_id': selected_address_id
    }

    return render(request, 'checkout.html', context)
def custom_404(request, exception):
    return render(request, '404.html', status=404)
@csrf_exempt
def create_order(request):
    if request.method == 'POST':
        try:
            user = request.user

            selected_ids = request.POST.getlist("selected_items[]")
            cart_items = CartItem.objects.filter(
                user=request.user,
                id__in=selected_ids
            )

            if not cart_items.exists():
                return JsonResponse({"error":"Cart is empty"},status = 400)
              
            total = sum(item.unit_price*item.quantity for item in cart_items)
            shipping = 50 if total>500 else 0
            coupon_id = request.session.get('coupon_id')
            discount = 0
            if coupon_id:
                try :
                    coupon = Coupon.objects.get(id=coupon_id,active=True)
                    discount = coupon.max_discount_amount
                except Coupon.DoesNotExist:
                    discount = 0
            final_amount = total+shipping-discount
            amount = int(final_amount*100)

            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
           

            payment = client.order.create({
                "amount": amount,  
                "currency": "INR",
                "payment_capture": "1",

            })
            return JsonResponse({
                'order':payment,
                'razorpay_key':settings.RAZORPAY_KEY_ID
            })
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    return JsonResponse({'error':'Invalid request method'},status=400)        
@login_required
def cancel_item(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id, order__user=request.user)
    order = item.order
    if item.status == 'Cancelled':
        messages.info(request, "This item is already fully cancelled")
        return redirect('order_detail', order_id=order.id)
    remaining = item.quantity - (item.returned_quantity or 0) - (item.cancelled_quantity or 0)
    if remaining <= 0:
        messages.warning(request, "No quantity left to cancel")
        return redirect('order_detail', order_id=order.id)
    if request.method == "POST":
        cancel_qty = int(request.POST.get("cancel_qty"))
        if cancel_qty <= 0 or cancel_qty > remaining:
            messages.error(request, "Invalid cancel quantity")
            return redirect('order_detail', order_id=order.id)
        item.cancelled_quantity = (item.cancelled_quantity or 0) + cancel_qty
        if item.cancelled_quantity == item.quantity:
            item.status = "Cancelled"
        else:
            item.status = "Partially Cancelled"
        item.save()
        variation = item.variation
        if variation:
            variation.stock += cancel_qty
            variation.save()

        order_items = order.items.all()
        new_subtotal = 0
        for i in order_items:
            cancelled = i.cancelled_quantity or 0
            returned = i.returned_quantity or 0
            final_qty = i.quantity - cancelled - returned
            new_subtotal += i.price * final_qty
        order.subtotal = new_subtotal
        order.total = order.subtotal - order.discount + order.shipping
        order.save()    

        refund_amount = item.price * cancel_qty
        if order.payment_method in ['Wallet', 'Razorpay']:
            credit_wallet(
                user=request.user,
                amount=refund_amount,
                description=f"Refund for cancelled {cancel_qty} item(s) in Order #{order.id}",
                source='refund',
                order=order
            )
        if not order.items.exclude(status="Cancelled").exists():
            order.status = "Cancelled"
            order.save()
        messages.success(request, f"{cancel_qty} item(s) cancelled successfully")
        return redirect('order_detail', order_id=order.id)
    return render(request, "user/cancel_item.html", {
        "item": item,
        "order": order,
        "remaining": remaining
    })
def payment_success(request):
    payment_id = request.GET.get('payment_id')
    user = request.user

    order = Order.objects.filter(user=user,status='Pending').last()

    if order:
        order.status = 'Paid'
        order.payment_method='razorpay'
        order.save()
    return render(request,'user/payment_sucess.html',{'order':order})    

def finalize_order(order,cart_items):
    for item in cart_items:
        variation = item.variation
        if variation:
            price,_=get_best_price(variation)

            if variation.stock<item.quantity:
                raise Exception("Insufficient stock")
            variation.stock-=item.quantity 
            variation.save()

        else:
            price = item.unit_price
        OrderItem.objects.create(
            order=order,
            product=item.product,
            variation=variation,
            quantity=item.quantity,
            price=price
        )  
    cart_items.delete()             
@login_required(login_url='login')
@never_cache
def place_orders(request):

    if request.method != 'POST':
        return redirect('shop')

    user = request.user
    payment_method = request.POST.get('payment_method')

    selected_address = request.POST.get('selected_address')

    if selected_address == "new":
        address = Address.objects.create(
            user=user,
            street=request.POST.get('street'),
            city=request.POST.get('city'),
            district=request.POST.get('district'),
            state=request.POST.get('state'),
            pincode=request.POST.get('pincode'),
        )
    else:
        address = Address.objects.get(id=selected_address, user=user)

    selected_item_ids = request.POST.getlist('selected_items[]')

    if selected_item_ids:
        cart_items = CartItem.objects.filter(user=user, id__in=selected_item_ids)
    else:
        cart_items = CartItem.objects.filter(user=user)

    if not cart_items.exists():
        messages.error(request, "Your cart is empty or no items selected.")
        return redirect('cart')

    subtotal = sum(item.unit_price * item.quantity for item in cart_items)
    shipping = 50 if subtotal > 500 else 0

    discount = Decimal('0.00')
    coupon = None
    coupon_id = request.session.get("coupon_id")

    if coupon_id:
        try:
            coupon = Coupon.objects.get(id=coupon_id, active=True)
            now = timezone.now()

            if coupon.valid_from and coupon.valid_from > now:
                messages.error(request, "Coupon is not active yet")
                request.session.pop('coupon_id', None)
                coupon = None
            elif coupon.valid_to and coupon.valid_to < now:
                messages.error(request, "Coupon has expired.")
                request.session.pop("coupon_id", None)
                coupon = None
            elif coupon.min_purchase_amount and subtotal < coupon.min_purchase_amount:
                messages.error(request, f"Minimum purchase of ₹{coupon.min_purchase_amount} required.")
                request.session.pop("coupon_id", None)
                coupon = None
            else:
                if coupon.discount_type == "flat":
                    if coupon.discount_value > subtotal:
                        messages.error(request, "Coupon value exceeds cart total.")
                        request.session.pop("coupon_id", None)
                        coupon = None
                    else:
                        discount = coupon.discount_value
                elif coupon.discount_type == "percentage":
                    discount = (subtotal * coupon.discount_value) / Decimal('100')
                    if coupon.max_discount_amount:
                        discount = min(discount, coupon.max_discount_amount)
        except Coupon.DoesNotExist:
            request.session.pop("coupon_id", None)

    total = max(subtotal + shipping - discount, Decimal('0.00'))          

    order = Order.objects.create(
        user=user,
        address=address,
        subtotal=subtotal,
        shipping=shipping,
        discount=discount,
        total=total,
        payment_method=payment_method,
        status="Pending",
    )
    payment = Payment.objects.create(
    user=user,
    order=order,
    payment_method=payment_method,
    status="Pending",
    amount=total
    )

    if payment_method == "razorpay":

        razorpay_payment_id = request.POST.get("razorpay_payment_id")

        if razorpay_payment_id:

            order.payment_method = "Razorpay"
            order.status = "Processing"
            order.razorpay_payment_id = razorpay_payment_id
            order.save()

            payment.transaction_id = razorpay_payment_id
            payment.status = "Success"
            payment.save()

            finalize_order(order, cart_items)

            if coupon:
                CouponUsage.objects.create(user=request.user,coupon=coupon)
                request.session.pop('coupon_id',None)
            request.session['order_id'] = order.id
            return redirect('order_confirmation')
        else:
            order.delete()
            return redirect('checkout')

    elif payment_method == "cod":
        if total >50000:
            messages.error(request,"COD not available for more than 50000")
            return redirect("checkout")
        order.payment_method = "Cash on Delivery"
        order.status = "Processing"
        order.save()
        payment.status = "Pending"
        payment.payment_method = "COD"
        payment.save()
        finalize_order(order, cart_items)
        if coupon:
            CouponUsage.objects.create(user=request.user,coupon=coupon)
            request.session.pop('coupon_id',None)
        request.session['order_id'] = order.id
        return redirect('order_confirmation')

    elif payment_method == "Wallet":

        first_item = cart_items.first()
        if cart_items.count() > 1:
            product_info = f"{first_item.product.name} + {cart_items.count()-1} more"
        else:
            product_info = first_item.product.name

        success = debit_wallet(
        user=request.user,
        amount=total,
        description=f"Payment for {product_info} (Order #{order.id})",
        source='order payment',
        order=order 
        )
        if success:

            order.payment_method = "Wallet"
            order.status = "Processing"
            order.save()
            payment.status = "Success"
            payment.payment_method = "Wallet"
            payment.transaction_id = f"WALLET-{order.id}"
            payment.save()
            finalize_order(order, cart_items)
            if coupon:
                CouponUsage.objects.create(user=request.user,coupon=coupon)
                request.session.pop('coupon_id',None)
            messages.success(request, "Payment successful using Wallet")
            request.session['order_id'] = order.id
            return redirect('order_confirmation')
        else:
            order.delete()
            messages.error(request, "Insufficient wallet balance")
            return redirect('checkout')
    order.delete()

    messages.error(request, "Invalid payment method")
    return redirect('checkout')


@csrf_exempt
def razorpay_webhook(request):

    if request.method == "POST":
        client = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )
        webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
        body = request.body
        signature = request.headers.get("X-Razorpay-Signature")
        try:
            client.utility.verify_webhook_signature(
                body,
                signature,
                webhook_secret
            )
            data = json.loads(body)
            if data["event"] == "payment.captured":
                payment_entity = data["payload"]["payment"]["entity"]["order_id"]
                razorpay_order_id = payment_entity["order_id"]
                razorpay_payment_id = payment_entity["id"]
                order = Order.objects.get(razorpay_order_id=razorpay_order_id)
                order.status = "SUCCESS"
                order.save()
                payment = Payment.objects.get(order=order)
                if payment.status != "Success":
                    payment.transaction_id = razorpay_payment_id
                    payment.status = "Success"
                    payment.save()
                    order.status = "Processing"
                    order.save()
            elif data["event"] == "payment.failed":
                payment_entity = data["payload"]["payment"]["entity"]["order_id"]
                order = Order.objects.get(razorpay_order_id=razorpay_order_id)
                payment = Payment.objects.get(order=order)
                order.status = "FAILED"
                order.save()
            return HttpResponse(status=200)
        except:
            return HttpResponse(status=400)
@login_required
def download_invoice_pdf(request, order_id):
    order = Order.objects.get(id=order_id, user=request.user)
    order_items = OrderItem.objects.filter(order=order)
    updated_items = []
    total = 0
    for item in order_items:
        cancelled = item.cancelled_quantity or 0
        returned = item.returned_quantity or 0
        remaining = item.quantity - cancelled - returned
        if remaining > 0:
            item.remaining_quantity = remaining
            item.subtotal = remaining * item.price
            total += item.subtotal
            updated_items.append(item)
    template_path = 'user/invoice.html'
    context = {
        'order': order,
        'order_items': updated_items,
        'address': order.address,
        'total': total,
    }
    template = get_template(template_path)
    html = template.render(context)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="invoice_{order.id}.pdf"'
    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse('Error generating PDF', status=500)
    return response 

@login_required
def return_item(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id, order__user=request.user)

    if item.status != "Delivered" and item.status != "Partially Returned":
        messages.warning(request, "Only delivered items can be returned")
        return redirect('myorders')

    remaining = item.quantity - item.returned_quantity

    if remaining <= 0:
        messages.warning(request, "All quantities already returned")
        return redirect('myorders')
    
    if request.method == 'POST':
        print("POST DATA:", request.POST)
        reason = request.POST.get('reason')
        qty = int(request.POST.get('return_qty'))
         
        if qty <= 0 or qty > remaining:
            messages.error(request, "Invalid return quantity")
            return redirect('myorders')

        ReturnRequest.objects.create(
            item=item,
            user=request.user,
            quantity=qty,
            reason=reason,
            status='Pending'
        )

        item.status = "Return Requested"
        item.save()

        messages.success(request, f"Return request sent for {qty} item(s)")
        return redirect('myorders')

    return render(request, 'user/return_item.html', {
        'item': item,
        'order': item.order,
        'remaining': remaining
    })       

@login_required
def return_requests(request):
    requests_list = ReturnRequest.objects.all().order_by('-created_at')
    return render(request,'admin_templates/return_requests.html',{'requests':requests_list})  

@login_required
def update_return_status(request, request_id, action):
    return_request = get_object_or_404(ReturnRequest, id=request_id)

    order = return_request.item.order
    item = return_request.item
    user = return_request.user

    if action == 'accept':

        return_request.status = 'Accepted'
        item.status = 'Returned'
        item.save()

        variation = item.variation
        if variation:
            variation.stock += item.quantity
            variation.save()

        refund_amount = item.price * item.quantity

        description = f"Refund for {item.product.name} (Order #{order.id})"

        if order.payment_method in ["Wallet", "Razorpay"]:
            credit_wallet(
                user=user,
                amount=refund_amount,
                description=description,
                source="refund",
                order=order
            )

            Notification.objects.create(
                user=user,
                message=f"₹{refund_amount} refunded for {item.product.name} (Order #{order.id})"
            )

        if not order.items.exclude(status="Returned").exists():
            order.status = 'Returned'
            order.save()

    elif action == 'reject':
        return_request.status = 'Rejected'

    return_request.save()
    return redirect('return_requests')


@login_required
def sales_report(request):
    today = timezone.localdate()
    filter_type = request.GET.get('filter_type', '')
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            start_date = end_date = today
    elif filter_type:
        if filter_type == 'daily':
            start_date = end_date = today
        elif filter_type == 'weekly':
            start_date = today - timedelta(days=7)
            end_date = today
        elif filter_type == 'monthly':
            start_date = today.replace(day=1)
            end_date = today
        else:
            start_date = end_date = today
    else:
        start_date = end_date = today
    start_datetime = timezone.make_aware(datetime.combine(start_date, time.min))
    end_datetime = timezone.make_aware(datetime.combine(end_date, time.max))
    orders = Order.objects.filter(
        created_at__gte=start_datetime,
        created_at__lte=end_datetime
    ).order_by('created_at')
    total_revenue = orders.aggregate(Sum('total'))['total__sum'] or 0
    total_orders = orders.count()
    total_discount = orders.aggregate(Sum('discount'))['discount__sum'] or 0
    sales_data = orders.annotate(date_only=TruncDate('created_at')) \
                       .values('date_only') \
                       .annotate(total=Sum('total')) \
                       .order_by('date_only')
    dates = [entry['date_only'].strftime('%d %b') for entry in sales_data if entry['date_only']]
    revenues = [float(entry['total']) for entry in sales_data if entry['date_only']]
    context = {
        'orders': orders,
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'total_discount': total_discount,
        'start_date': start_date,
        'end_date': end_date,
        'filter_type': filter_type,
        'chart_dates': dates,
        'chart_revenues': revenues,
    }
    return render(request, 'admin_templates/sales_report.html', context)


@login_required
def download_sales_pdf(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    filter_type = request.GET.get('filter_type')
    today = timezone.localdate()
    if start_date and end_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
    elif filter_type == 'daily':
        start_date = end_date = today
    elif filter_type == 'weekly':
        start_date = today - timedelta(days=7)
        end_date = today
    elif filter_type == 'monthly':
        start_date = today.replace(day=1)
        end_date = today
    else:
        start_date = end_date = today
    start_datetime = timezone.make_aware(datetime.combine(start_date, time.min))
    end_datetime = timezone.make_aware(datetime.combine(end_date, time.max))
    orders = Order.objects.filter(
        created_at__gte=start_datetime,
        created_at__lte=end_datetime
    ).order_by('created_at')
    total_orders = orders.count()
    total_revenue = orders.aggregate(Sum('total'))['total__sum'] or 0
    total_discount = orders.aggregate(Sum('discount'))['discount__sum'] or 0
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="sales_report.pdf"'
    doc = SimpleDocTemplate(response, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []
    elements.append(Paragraph("Sales Report", styles['Title']))
    elements.append(Paragraph(f"From: {start_date} To: {end_date}", styles['Normal']))
    elements.append(Paragraph(f"Total Orders: {total_orders}", styles['Normal']))
    elements.append(Paragraph(f"Total Revenue: Rs.{total_revenue:.2f}", styles['Normal']))
    elements.append(Paragraph(f"Total Discount: Rs.{total_discount:.2f}", styles['Normal']))
    elements.append(Paragraph(" ", styles['Normal']))
    data = [["Order ID", "Customer", "Total Amount", "Discount", "Date"]]
    for order in orders:
        created = order.created_at.strftime("%Y-%m-%d") if order.created_at else "-"
        data.append([
            str(order.id),
            str(order.user.username),
            f"{order.total}",
            f"{order.discount or 0}",
            created
        ])
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ]))
    elements.append(table)
    doc.build(elements)
    return response


@login_required
def download_sales_excel(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    filter_type = request.GET.get('filter_type')
    today = timezone.localdate()
    if start_date and end_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
    elif filter_type == 'daily':
        start_date = end_date = today
    elif filter_type == 'weekly':
        start_date = today - timedelta(days=7)
        end_date = today
    elif filter_type == 'monthly':
        start_date = today.replace(day=1)
        end_date = today
    else:
        start_date = end_date = today
    start_datetime = timezone.make_aware(datetime.combine(start_date, time.min))
    end_datetime = timezone.make_aware(datetime.combine(end_date, time.max))
    orders = Order.objects.filter(
        created_at__gte=start_datetime,
        created_at__lte=end_datetime
    ).order_by('-created_at')
    total_orders = orders.count()
    total_revenue = orders.aggregate(Sum('total'))['total__sum'] or 0
    total_discount = orders.aggregate(Sum('discount'))['discount__sum'] or 0
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "Sales Report"
    worksheet.append(["Sales Report"])
    worksheet.append([f"From: {start_date} To: {end_date}"])
    worksheet.append([f"Total Orders: {total_orders}"])
    worksheet.append([f"Total Revenue: ₹{total_revenue:.2f}"])
    worksheet.append([f"Total Discount: ₹{total_discount:.2f}"])
    worksheet.append([])
    headers = ["Order ID", "Customer", "Total Amount", "Discount", "Date"]
    worksheet.append(headers)
    for cell in worksheet[7]:
        cell.font = Font(bold=True)
    for order in orders:
        created = order.created_at.strftime("%Y-%m-%d") if order.created_at else "-"
        worksheet.append([
            order.id,
            order.user.username,
            float(order.total),
            float(order.discount or 0),
            created
        ])
  
    for column_cells in worksheet.columns:
        length = max(len(str(cell.value)) if cell.value else 0 for cell in column_cells)
        worksheet.column_dimensions[column_cells[0].column_letter].width = length + 5
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response['Content-Disposition'] = 'attachment; filename="sales_report.xlsx"'
    workbook.save(response)
    return response

@login_required
def notifications_page(request):
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'user/notification_page.html', {'notifications': notifications})


def download_shipping_pdf(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="shipping_{order.id}.pdf"'
    p = canvas.Canvas(response)
    p.setFont("Helvetica-Bold", 14)
    p.drawString(200, 800, "Shipping Label")
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, 750, "FROM:")
    p.setFont("Helvetica", 11)
    p.drawString(50, 730, "Unikart Store")
    p.drawString(50, 710, "Chennai, Tamil Nadu")
    p.drawString(50, 690, "Phone: 9876543210")
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, 650, "TO:")
    p.setFont("Helvetica", 11)
    p.drawString(50, 630, f"{order.user.username}")
    
    if order.address:
        p.drawString(50, 590, f"{order.address.street}")
        p.drawString(50, 570, f"{order.address.city}, {order.address.state}")
        p.drawString(50, 550, f"Pincode: {order.address.pincode}")
        p.drawString(50, 610, f"{order.user.profile.phone}")
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, 500, f"Order ID: #{order.id}")

    p.showPage()
    p.save()

    return response    


def admin_download_invoice(request, order_id):
    order = get_object_or_404(Order, id=order_id)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="invoice_{order.id}.pdf"'

    p = canvas.Canvas(response)

    # ===== TITLE =====
    p.setFont("Helvetica-Bold", 16)
    p.drawString(200, 800, "INVOICE")

    # ===== STORE INFO =====
    p.setFont("Helvetica", 11)
    p.drawString(50, 770, "Unikart Store")
    p.drawString(50, 750, "Chennai, Tamil Nadu")
    p.drawString(50, 730, "Phone: 9876543210")

    # ===== CUSTOMER INFO =====
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, 690, "Bill To:")

    p.setFont("Helvetica", 11)
    p.drawString(50, 670, f"{order.user.username}")
    p.drawString(50, 650, f"{order.user.email}")
    p.drawString(50, 630, f"{order.user.profile.phone}")

    if order.address:
        p.drawString(50, 610, f"{order.address.street}")
        p.drawString(50, 590, f"{order.address.city}, {order.address.state}")
        p.drawString(50, 570, f"Pincode: {order.address.pincode}")

    # ===== ORDER INFO =====
    p.setFont("Helvetica-Bold", 12)
    p.drawString(350, 690, f"Order ID: #{order.id}")
    p.drawString(350, 670, f"Payment: {order.payment_method}")

    # ===== TABLE HEADER =====
    y = 520
    p.setFont("Helvetica-Bold", 11)
    p.drawString(50, y, "Product")
    p.drawString(250, y, "Qty")
    p.drawString(300, y, "Price")
    p.drawString(380, y, "Total")

    # ===== ITEMS =====
    y -= 20
    p.setFont("Helvetica", 10)

    for item in order.items.all():
        p.drawString(50, y, item.product.name[:25])
        p.drawString(250, y, str(item.quantity))
        p.drawString(300, y, f"Rs.{item.price}")
        p.drawString(380, y, f"Rs.{item.price * item.quantity}")
        y -= 20

    # ===== TOTAL =====
    y -= 20
    p.setFont("Helvetica-Bold", 12)
    p.drawString(300, y, "Total:")
    p.drawString(380, y, f"Rs.{order.total}")

    p.showPage()
    p.save()

    return response    