from django.utils import timezone
from django.utils import timezone
from django.db.models import Sum, F
from store.models import Order, OrderItem, DailySalesReport, ProductSalesReport, CategorySalesReport,Category

def get_best_price(variation):

    original_price = variation.original_price
    best_price = original_price
    best_discount = 0

    now = timezone.localtime()

    all_offers = variation.product.offer_on_this_product.all()

    product_offers = variation.product.offer_on_this_product.filter(
        is_active=True,
        valid_from__lte=now,
        valid_to__gte=now
    )
    
    for offer in product_offers:
      
        if offer.discount_type == "flat":
            discount_amount = min(offer.dis_value, original_price)
        else:
            discount_amount = (original_price * offer.dis_value) / 100

        price = original_price - discount_amount
        price = max(price, 0)

        discount = round((discount_amount / original_price) * 100) if original_price else 0

        if price < best_price:
            best_price = price
            best_discount = discount

   
    category = variation.product.category

    if category:

        category_offers = category.offer_on_this_category.filter(
            is_active=True,
            valid_from__lte=now,
            valid_to__gte=now
        )
     
        for offer in category_offers:

            if offer.discount_type == "flat":
                discount_amount = min(offer.dis_value, original_price)
            else:
                discount_amount = (original_price * offer.dis_value) / 100

            price = original_price - discount_amount
            price = max(price, 0)

            discount = round((discount_amount / original_price) * 100) if original_price else 0

            if price < best_price:
                best_price = price
                best_discount = discount


    return round(best_price, 2), best_discount


def generate_daily_sales_report(date=None):
    if not date:
        date = timezone.now().date()
    
    orders = Order.objects.filter(created_at__date=date, status='Delivered')
    total_orders = orders.count()
    total_products_sold = orders.aggregate(Sum('items__quantity'))['items__quantity__sum'] or 0
    total_revenue = orders.aggregate(Sum('total'))['total__sum'] or 0

    DailySalesReport.objects.update_or_create(
        date=date,
        defaults={
            'total_orders': total_orders,
            'total_products_sold': total_products_sold,
            'total_revenue': total_revenue
        }
    )

  
    products = ProductSalesReport.objects.all()
    for ps in products:
        total_qty = OrderItem.objects.filter(product=ps.product, order__status='Delivered').aggregate(Sum('quantity'))['quantity__sum'] or 0
        total_rev = OrderItem.objects.filter(product=ps.product, order__status='Delivered').aggregate(
            revenue=Sum(F('quantity') * F('price'))
        )['revenue'] or 0
        ProductSalesReport.objects.update_or_create(
            product=ps.product,
            defaults={
                'total_quantity_sold': total_qty,
                'total_revenue': total_rev
            }
        )

   
    for category in Category.objects.all():
        CategorySalesReport.objects.get_or_create(category=category)
    for category_report in CategorySalesReport.objects.all():
        items = OrderItem.objects.filter(
            product__category=category_report.category,  
            order__status='Delivered'                  
        )
        total_quantity = items.aggregate(Sum('quantity'))['quantity__sum'] or 0
        total_revenue = items.aggregate(Sum('price'))['price__sum'] or 0

        category_report.total_quantity_sold = total_quantity
        category_report.total_revenue = total_revenue
        category_report.save()