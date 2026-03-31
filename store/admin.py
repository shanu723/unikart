from django.contrib import admin 
from .models import *

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display=['id','name','status','created_at']

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display=['id','name','status',]
@admin.register(Highlight)
class HighlightAdmin(admin.ModelAdmin):
    pass
@admin.register(Variation)
class VariationAdmin(admin.ModelAdmin):
    list_display = ('product', 'size','original_price', 'offer')
    list_editable = ('offer',)

@admin.register(ProductImages)
class ProductImagesAdmin(admin.ModelAdmin):
    pass

@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display=['title']

@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display=['city','pincode','district','state']

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("user__username", "user__email", "id")
    


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product", "quantity", "price")
    list_filter = ("product",)    

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "discount_type","discount_value","max_discount_amount", "active", "valid_from", "valid_to")
    search_fields = ("code",)
    list_filter = ("active",)

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('user', 'balance', 'updated_at') 

@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'transaction_id',
        'user',
        'transaction_type',
        'source',
        'amount',
        'created_at',
    )

@admin.register(DailySalesReport)
class DailySalesReportAdmin(admin.ModelAdmin):
    list_display = ('date','total_orders','total_products_sold','total_revenue')
    ordering = ['-date']

@admin.register(ProductSalesReport)
class ProductSalesReportAdmin(admin.ModelAdmin):
    list_display = ('product','total_quantity_sold','total_revenue')
    ordering = ['-total_quantity_sold']

@admin.register(CategorySalesReport)
class CategorySalesReportAdmin(admin.ModelAdmin):
    list_display = ('category','total_quantity_sold','total_revenue')
    ordering = ['-total_revenue']            
@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('order','status','payment_method')
    ordering = ['-created_at']

@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display=('order_item','amount','reason')
    ordering = ['-created_at']    
