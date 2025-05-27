"""
URL configuration for bluemoon project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.shortcuts import render
from core.models import *  # sửa lại path import theo app của bạn
from django.utils import timezone
from django.db.models import Sum, Count, Q, OuterRef, Subquery, Exists
from datetime import datetime
from django.template.loader import render_to_string
from django.http import JsonResponse, HttpResponse

def ketoan_view(request):
    # Tổng số chủ hộ
    total_residents = User.objects.filter(role='chu_ho').count()
    today = timezone.now().date()
    now = timezone.now()

    # Xác định mốc thời gian
    start_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    if now.month == 12:
        start_of_next_month = start_of_this_month.replace(year=now.year + 1, month=1)
    else:
        start_of_next_month = start_of_this_month.replace(month=now.month + 1)

    if now.month == 1:
        start_of_last_month = start_of_this_month.replace(year=now.year - 1, month=12)
    else:
        start_of_last_month = start_of_this_month.replace(month=now.month - 1)

    # Tổng doanh thu tháng này
    total_revenue = Payment.objects.filter(
        paid_at__gte=start_of_this_month,
        paid_at__lt=start_of_next_month,
        status='paid'
    ).aggregate(total=Sum('fee__amount'))['total'] or 0

    # Doanh thu tháng trước
    last_month_revenue = Payment.objects.filter(
        paid_at__gte=start_of_last_month,
        paid_at__lt=start_of_this_month,
        status='paid'
    ).aggregate(total=Sum('fee__amount'))['total'] or 0

    # Tính phần trăm thay đổi
    if last_month_revenue == 0:
        change_percent = None
    else:
        change_percent = ((total_revenue - last_month_revenue) / last_month_revenue) * 100

    # Đã thanh toán trong tháng này
    paid_count = Payment.objects.filter(
        paid_at__gte=start_of_this_month,
        paid_at__lt=start_of_next_month,
        status='paid'
    ).count()

    # Chưa thanh toán trong tháng này
    unpaid_count = Payment.objects.filter(
        paid_at__gte=start_of_this_month,
        paid_at__lt=start_of_next_month,
        status='unpaid'
    ).count()

    # Tổng phí cần thu trong tháng
    total_due = Fee.objects.filter(
        due_date__gte=start_of_this_month,
        due_date__lt=start_of_next_month
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Tỷ lệ thu
    collection_rate = (total_revenue / total_due) * 100 if total_due > 0 else None

    # Lấy danh sách nhân khẩu
    members = HouseholdMember.objects.all()

    # Lấy số hoá đơn quá hạn
    overdue_bills = Fee.objects.filter(
    due_date__lt=today
    ).exclude(
    payments__status='paid'
    ).distinct().count()

    # Tổng nợ: các hóa đơn quá hạn chưa thanh toán
    paid_subquery = Payment.objects.filter(
    fee=OuterRef('pk'),
    status='paid'
    )

    total_debt = Fee.objects.filter(
        due_date__lt=today
    ).annotate(
        has_paid=Exists(paid_subquery)
    ).filter(
        has_paid=False
    ).aggregate(
        total=Sum('amount')
    )['total'] or 0

    households_need_contact = Household.objects.filter(
    payments__fee__due_date__lt=today,
    payments__status='unpaid'
    ).distinct()

    need_contact_count = households_need_contact.count()
    search_query = request.GET.get('q', '').strip()
    if search_query:
        members = members.filter(full_name__icontains=search_query)


    return render(request, 'ketoan.html', {
        'total_residents': total_residents,
        'total_revenue': total_revenue,
        'change_percent': change_percent,
        'paid_count': paid_count,
        'unpaid_count': unpaid_count,
        'collection_rate': collection_rate,
        'members': members,
        'overdue_bills': overdue_bills,
        'total_debt' : total_debt,
        'need_contact_count': need_contact_count,
        'search_query': search_query,
    })

def search_residents(request):
    query = request.GET.get('q', '')
    if query:
        results = HouseholdMember.objects.filter(full_name__icontains=query)
    else:
        results = HouseholdMember.objects.all()

    html = render_to_string('partials/_resident_table_rows.html', {'members': results})
    return JsonResponse({'html': html})


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', ketoan_view, name='home'),  # xử lý root URL
    path('ketoan/', ketoan_view, name='ketoan'),
    path('search-residents/', search_residents, name='search_residents'),
]

