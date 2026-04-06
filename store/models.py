from django.db import models
from django.core.validators import MinValueValidator, FileExtensionValidator,ValidationError
from django.utils import timezone
import uuid, os
from PIL import Image,ImageOps
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from django.db.models import Min





class UserOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    


class Category(models.Model):
    name = models.CharField(max_length=100)
    status=models.BooleanField(default=False)
    created_at=models.DateTimeField(auto_now_add=True)
    offer=models.ForeignKey('Offer',on_delete=models.SET_NULL,blank=True,null=True,related_name='products_with_this_category')
    def __str__(self):
        return self.name

class UserProfile(models.Model): 
    user=models.OneToOneField(User,on_delete=models.CASCADE,related_name='profile') 
    is_blocked=models.BooleanField(default=False)
    phone = models.CharField(max_length=15, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    profile_photo = models.ImageField(upload_to='profile_photos/',default='profile_photos/default.jpg', blank=True, null=True)

    referral_code = models.CharField(max_length=10, null=True, blank=True,unique=True)
    referred_by = models.ForeignKey('self',on_delete=models.SET_NULL,null=True,blank=True)

    def __str__(self): 
        return self.user.username

    def save(self,*args,**kwargs):
        if not self.referral_code:
            self.referral_code = str(uuid.uuid4())[:8].upper()
        super().save(*args,**kwargs)        

@receiver(post_save,sender=User)
def create_user_profile(sender,instance,created,**kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)  


class Address(models.Model):
    user=models.ForeignKey(User,on_delete=models.CASCADE,related_name='address')
    street= models.CharField(max_length=100,blank=True,null=True)
    city=models.CharField(max_length=100,blank=True,null=True)
    district=models.CharField(max_length=100,blank=True,null=True) 
    state=models.CharField(max_length=100,blank=True,null=True)
    pincode=models.CharField(max_length=6,blank=True,null=True)
    
    is_default=models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} - {self.city}"

class Product(models.Model):
    name=models.CharField(max_length=100,blank=False,null=False)
    brand=models.CharField(max_length=100,blank=True,null=True)
    
    category=models.ForeignKey(Category,on_delete=models.CASCADE,null=True,blank=True)
    offer=models.ForeignKey('Offer',on_delete=models.CASCADE,null=True,blank=True,related_name='products_with_this_offer')
    created_at=models.DateTimeField(auto_now_add=True)
    status=models.BooleanField(null=False,default=False)
    description=models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.name}"

class Variation(models.Model):
    SIZE_CHOICES=[
        ('32','32 inch'),
        ('43','43 inch'),
        ('50','50 inch'),
        ('60','60 inch')
    ]
    size=models.CharField(max_length=10,choices=SIZE_CHOICES)
    product=models.ForeignKey(Product,on_delete=models.CASCADE)    
    
    original_price=models.DecimalField(max_digits=10,decimal_places=2,validators=[MinValueValidator(0.01)])
    stock=models.PositiveIntegerField(default=0)
    created_at=models.DateTimeField(auto_now_add=True)
    status=models.BooleanField(null=False, default=True)
    offer=models.ForeignKey('Offer',on_delete=models.SET_NULL,blank=True,null=True)
    def is_in_stock(self):
        return self.stock > 0
    def __str__(self):
        return f"{self.product.name}-{self.original_price}-{self.size}"

    
class Highlight(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='highlights')
    key = models.CharField(max_length=50)    
    value = models.CharField(max_length=200) 

    def __str__(self):
        return f"{self.key}: {self.value}"



def getfilename(instance,filename):
    ext=filename.split('.')[-1] 
    filename=f"{uuid.uuid4()}.{ext}"
    return os.path.join('images',filename)       

class ProductImages(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='productimages')
    product_image = models.ImageField(upload_to=getfilename, validators=[FileExtensionValidator(allowed_extensions=['jpg','png','webp','jpeg'])])
    is_primary = models.BooleanField(default=False)
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)    
        try:
            img = Image.open(self.product_image.path)
            max_size = (800,800)
            
            img = ImageOps.fit(img,max_size,image.LANCZOS)
            img.save(self.product_image.path)
            
        except Exception as e:
            print(f"Image resize failed:{e}")     

    def __str__(self):
        return f"{self.product.name} - Image"


class Offer(models.Model):

    title = models.CharField(max_length=100, null=True, blank=True)
    DISCOUNT_CHOICES = (
        ('percentage', 'Percentage'),
        ('flat', 'Flat')
    )
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_CHOICES)
    dis_value = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_to = models.DateTimeField()
    OFFER_TYPES = (
        ('category', 'Category'),
        ('product', 'Product')
    )
    offer_type = models.CharField(max_length=30, choices=OFFER_TYPES)
    category = models.ForeignKey(Category,on_delete=models.CASCADE,null=True,blank=True,related_name='offer_on_this_category')
    product = models.ForeignKey(Product,on_delete=models.CASCADE,null=True,blank=True,related_name='offer_on_this_product'
    )
    def __str__(self):
        return self.title or f"Offer {self.id}"
 
    def clean(self):
       
        if self.discount_type == 'percentage':
            if self.dis_value <= 0 or self.dis_value > 90:
                raise ValidationError("Percentage discount must be between 1 and 90")
     
        elif self.discount_type == 'flat':
            if self.dis_value <= 0:
                raise ValidationError("Flat discount must be greater than 0")
          
            if self.offer_type == 'product' and self.product:

                min_price = self.product.variation_set.aggregate(Min('original_price'))['original_price__min']

                if min_price and self.dis_value > min_price:
                    raise ValidationError(f"Flat discount cannot exceed product price (₹{min_price})")
            
            if self.offer_type == 'category' and self.category:
                min_price = Variation.objects.filter(product__category=self.category).aggregate(Min('original_price'))['original_price__min']
                if min_price and self.dis_value > min_price:
                    raise ValidationError(
                        f"Flat discount cannot exceed lowest product price in this category (₹{min_price})"
                    )

        if self.valid_to <= self.valid_from:

            raise ValidationError(
                "Valid To must be greater than Valid From"
            )

    def is_valid(self):
        now = timezone.now()
        return self.is_active and self.valid_from <= now <= self.valid_to

    def get_status(self):
        now = timezone.localtime()
        if not self.is_active:
            return 'Inactive'
        elif self.valid_from > now:
            return 'Upcoming'
        elif self.valid_to < now:
            return 'Expired'
        else:
            return 'Active'
class Order(models.Model):
    STATUS_CHOICES = [
        ("Pending", "Pending"),
        ("Processing", "Processing"),
        ("Confirmed", "Confirmed"),
        ("Shipped", "Shipped"),
        ("Delivered", "Delivered"),
        ("Cancelled", "Cancelled"),
    ]
    user=models.ForeignKey(User,on_delete=models.CASCADE)
    address=models.ForeignKey(Address,on_delete=models.SET_NULL,null=True,blank=True)

    customer_name = models.CharField(max_length=200,blank =True)
    customer_email = models.EmailField(blank=True)
    customer_phone = models.CharField(max_length = 15,blank = True)

    street = models.CharField(max_length=100,blank=True)
    city = models.CharField(max_length=100,blank = True)
    district = models.CharField(max_length=100,blank = True)
    state = models.CharField(max_length = 100,blank = True)
    pincode = models.CharField(max_length=6,blank = True)

    created_at=models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default="Pending")
    subtotal = models.DecimalField(max_digits=10, decimal_places = 2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places =2,default=0)
    shipping = models.DecimalField(max_digits=10, decimal_places=2,default=0)
    total = models.DecimalField(max_digits=10,decimal_places=2,default=0)
    payment_method = models.CharField(max_length=50,blank=True,null=True)
    def __str__(self):
        return f"Order{self.id} by {self.user.username}"

class OrderItem(models.Model):
    STATUS_CHOICES = [
        ("Ordered","Ordered"),
        ("Shipped","Shipped"),
        ("Delivered","Delivered"),
        ("Cancelled","Cancelled"),
        ("Returned","Returned"),
        ("Partially Cancelled","Partially Cancelled"), 
        ("Partially Returned","Partially Returned"),
    ]

    order=models.ForeignKey(Order,related_name='items',on_delete=models.CASCADE)
    product=models.ForeignKey(Product,on_delete=models.CASCADE)
    variation = models.ForeignKey(Variation, on_delete=models.CASCADE, null=True, blank=True)
    quantity=models.PositiveIntegerField(default=1)
    returned_quantity = models.PositiveIntegerField(default=0)
    cancelled_quantity = models.PositiveIntegerField(default=0)
    price=models.DecimalField(max_digits=10,decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Ordered")

    def __str__(self):
        return f"{self.quantity}*{self.product.name}"

class ReturnRequest(models.Model):
    STATUS_CHOICES=[
        ('Pending','Pending'),
        ('Accepted','Accepted'),
        ('Rejected','Rejected'),
    ]      
    item = models.ForeignKey(OrderItem, on_delete=models.CASCADE)
    user = models.ForeignKey(User,on_delete=models.CASCADE)
    reason = models.TextField()
    quantity = models.PositiveIntegerField()
    status = models.CharField(max_length=10,choices=STATUS_CHOICES,default='Pending')
    created_at = models.DateTimeField(default=timezone.now) 

    def __str__(self):
        return f"REturn Request for Order #{self.item.id}({self.status})"

class CartItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    variation = models.ForeignKey(Variation,on_delete=models.CASCADE,null=True,blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2,default=0)

    def __str__(self):
        return f"{self.product.name} ({self.quantity})"        

class Coupon(models.Model):
    DISCOUNT_TYPE_CHOICES = [
        ('flat', 'Flat Amount'),
        ('percentage', 'Percentage'),
    ]

    code = models.CharField(max_length=50, unique=True)
    discount_type = models.CharField(max_length=20,choices = DISCOUNT_TYPE_CHOICES,default='flat')
    discount_value = models.DecimalField(max_digits=10,decimal_places=2)
    max_discount_amount = models.DecimalField(max_digits=10,decimal_places=2,null=True,blank=True)
    min_purchase_amount = models.DecimalField(max_digits=10,decimal_places=2,null=True,blank=True)
    active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_to = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.code      

    def calculate_discount(self, subtotal):
        if self.min_purchase_amount and subtotal < self.min_purchase_amount:
            return Decimal('0')
        if self.discount_type == "flat":
            return min(self.discount_value, subtotal)
        if self.discount_type == "percentage":
            discount = (subtotal * self.discount_value) / Decimal('100')
        if self.max_discount_amount:
            discount = min(discount, self.max_discount_amount)
            return discount
        return Decimal('0')      

class CouponUsage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE)
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'coupon')  
        
    def __str__(self):
        return f"{self.user.username} used {self.coupon.code}"          


class Wishlist(models.Model):
    user = models.ForeignKey(User,on_delete=models.CASCADE)
    product = models.ForeignKey(Product,on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.product.name}"

class EmailOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    email = models.EmailField()
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        return timezone.now() > self.created_at + timezone.timedelta(minutes=5)

    def __str__(self):
        return f"{self.user.username} - {self.email}" 

class Wallet(models.Model):

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s Wallet"

    def add_money(self, amount):
        amount = Decimal(amount)
        self.balance += amount
        self.save()
    def deduct_money(self, amount):
        amount = Decimal(amount)
        if self.balance >= amount:
            self.balance -= amount
            self.save()
            return True

        return False              
        
class WalletTransaction(models.Model):

    TRANSACTION_TYPE = (('credit', 'Credit'), ('debit', 'Debit'))
    SOURCE_TYPE = (('wallet_recharge', 'Wallet Recharge'), ('order_payment', 'Order Payment'), ('refund', 'Refund'),('signup_bonus', 'Signup Bonus'),
    ('referral_bonus', 'Referral Bonus'),)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="wallet_transactions")
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="transactions")
    order = models.ForeignKey('Order', on_delete=models.SET_NULL, null=True, blank=True)
    transaction_id = models.CharField(max_length=50, unique=True, editable=False)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPE)
    source = models.CharField(max_length=20, choices=SOURCE_TYPE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    description = models.TextField(blank=True, null=True)


    def save(self, *args, **kwargs):
        if not self.transaction_id:
            self.transaction_id = "TXN" + uuid.uuid4().hex[:10].upper()
        super().save(*args, **kwargs)


    def __str__(self):
        return f"{self.transaction_id} - {self.user.username}"


class DailySalesReport(models.Model):
    date = models.DateField(unique=True)

    total_orders = models.PositiveIntegerField(default=0)
    total_products_sold = models.PositiveIntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=15, decimal_places=2, default=0)


    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']    
    def __str__(self):
        return f"Sales Report - {self.date}"

class ProductSalesReport(models.Model):
    product = models.OneToOneField('Product',on_delete = models.CASCADE)
    total_quantity_sold = models.PositiveIntegerField(default = 0)
    total_revenue = models.DecimalField(max_digits=15,decimal_places=2,default=0)

    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-total_quantity_sold']

    def __str__(self):
        return f"{self.product.name} - Sales Report"

class CategorySalesReport(models.Model):
    category = models.OneToOneField('Category',on_delete=models.CASCADE)

    total_quantity_sold = models.PositiveIntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=15,decimal_places=2,default=0)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-total_revenue']

    def __str__(self):
        return f"{self.category.name}-Sales Report"
        

class Payment(models.Model):

    STATUS_CHOICES = [
        ('Pending','Pending'),
        ('Success','Success'),
        ('Failed','Failed'),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payments")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    payment_method = models.CharField(max_length=50)   
    transaction_id = models.CharField(max_length=200, blank=True, null=True,unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Pending")
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"Payment {self.id} - Order {self.order.id}"

class Refund(models.Model):

    STATUS_CHOICES = [
        ('Pending','Pending'),
        ('Approved','Approved'),
        ('Completed','Completed'),
        ('Rejected','Rejected'),
    ]
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name="refunds")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Pending")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Refund for OrderItem {self.order_item.id}"        

class Notification(models.Model):
    user = models.ForeignKey(User,on_delete=models.CASCADE,related_name='notifications')
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.message        