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
from django.db.models import Sum, Count, Q, OuterRef, Subquery, Exists, F
from datetime import datetime
from django.template.loader import render_to_string
from django.http import JsonResponse, HttpResponse
from core.forms import FeeForm
import datetime
import calendar
from openpyxl import Workbook
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from datetime import datetime
from django.shortcuts import redirect, get_object_or_404

import json
from django.db import connection
from django.shortcuts import redirect


@csrf_exempt
def homeowner_view(request):
    if not request.session.get('user_id') or request.session.get('role') != 'chu_ho':
        return redirect('/login')

    user_id = request.session['user_id']
    user = User.objects.get(id=user_id)
    household = Household.objects.filter(head=user).first()

    # Phí chung hoặc phí riêng áp dụng cho hộ đó
    applicable_fees = Fee.objects.filter(
        is_common=True
    ) | Fee.objects.filter(households=household)

    fee_status_list = []
    for fee in applicable_fees.distinct():
        payment = Payment.objects.filter(fee=fee, household=household).first()
        status = payment.status if payment else 'unpaid'
        fee_status_list.append({
            'title': fee.title,
            'amount': f"${fee.amount:,.0f}",
            'status': status
        })

    return render(request, 'homeowner.html', {
        'fullname': user.fullname,
        'apartment_number': household.household_number,
        'fee_status_list': fee_status_list
    })

@csrf_exempt
def ketoan_view(request):
    if not request.session.get('user_id') or request.session.get('role') != 'thu_ky':
        return redirect('/login')
    
    if request.method == 'GET' and request.headers.get('x-requested-with') == 'XMLHttpRequest' and 'month' in request.GET:
        month = request.GET.get("month")
        try:
            year, month = map(int, month.split("-"))
            start_date = datetime.date(year, month, 1)
            last_day = calendar.monthrange(year, month)[1]
            end_date = datetime.date(year, month, last_day)
        except:
            return HttpResponse("Tháng không hợp lệ", status=400)

    # Lấy các khoản phí đến hạn trong tháng
        fees = Fee.objects.filter(due_date__range=(start_date, end_date)).order_by('due_date')

    # Tạo Excel
        wb = Workbook()
        ws = wb.active
        ws.title = "Báo cáo phí"

        ws.append(["Căn hộ", "Loại phí", "Số tiền", "Hạn đóng", "Trạng thái", "Ngày thanh toán"])

        for fee in fees:
            payments = fee.payments.all()
            for payment in payments:
                ws.append([
                    payment.household.household_number,
                    fee.title,
                    float(fee.amount),
                    fee.due_date.strftime("%d/%m/%Y"),
                    payment.get_status_display(),
                    payment.paid_at.strftime("%d/%m/%Y %H:%M") if payment.paid_at else ''
                ])

        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        filename = f"bao_cao_phi_{year}_{month:02}.xlsx"
        response['Content-Disposition'] = f'attachment; filename=\"{filename}\"'
        wb.save(response)
        return response

    # Tổng số chủ hộ
    total_residents = User.objects.filter(role='chu_ho').count()
    now = timezone.localtime(timezone.now())
    today = now.date()

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
    fees = Fee.objects.all()
    payments = Payment.objects.select_related('fee', 'household').all()

    households = Household.objects.all()
    form = FeeForm()
    if request.method == 'POST' and request.headers.get('x-requested-with') == 'XMLHttpRequest':
        form = FeeForm(request.POST)
        if form.is_valid():
            user_id = request.session.get('user_id')
            if not user_id:
                return JsonResponse({'success': False, 'message': 'Người dùng chưa đăng nhập.'}, status=403)

            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return JsonResponse({'success': False, 'message': 'Không tìm thấy người dùng.'}, status=404)

            fee = form.save(commit=False)
            fee.created_by = user
            fee.created_at = datetime.now()

            # Xử lý phí chung hay riêng
            is_common = request.POST.get('is_common', 'true') == 'true'
            fee.is_common = is_common
            fee.save()

            if not is_common:
                household_ids = request.POST.getlist('households') # Nếu cần import
                households = Household.objects.filter(id__in=household_ids)
                fee.households.set(households)  # thiết lập quan hệ N-N

            return JsonResponse({
                'success': True,
                'id': str(fee.id),
                'title': fee.title,
                'amount': float(fee.amount),
                'type': fee.type,
                'due_date': fee.due_date.strftime('%Y-%m-%d'),
                'description': fee.description or '',
                'is_common': fee.is_common
            })
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)

    # Nếu là GET, render trang kế toán
    if not request.session.get('user_id') or request.session.get('role') != 'thu_ky':
        return redirect('/login')
    
    if request.method == 'GET' and request.headers.get('x-requested-with') == 'XMLHttpRequest' and request.GET.get('debt') == '1':

        today = now.date()

        unpaid_payments = Payment.objects.filter(
            status='unpaid',
            fee__due_date__lt=today
        ).select_related('fee', 'household__head')

        wb1 = Workbook()
        ws1 = wb1.active
        ws1.title = "Danh sách nợ"

        ws1.append(["Căn hộ", "Chủ hộ", "Loại phí", "Số tiền", "Hạn đóng"])

        for payment in unpaid_payments:
            household = payment.household
            head_name = household.head.fullname if household and household.head else "Không rõ"
            fee = payment.fee
            ws1.append([
                household.household_number,
                head_name,
                fee.title,
                float(fee.amount),
                fee.due_date.strftime("%d/%m/%Y")
            ])

        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="danh_sach_no.xlsx"'
        wb1.save(response)
        return response
    user_id = request.session.get('user_id')
    user = User.objects.get(id=user_id)


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
        'fees': fees,
        'payments': payments,
        'fullname': user.fullname,
        'households': households,
        'form': form,
    })

def update_payment(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            payment_id = data.get('payment_id')
            paid_at = data.get('paid_at')
            status = data.get('status')
            method = data.get('method')

            payment = Payment.objects.get(id=payment_id)
            payment.paid_at = paid_at
            payment.status = status
            payment.method = method
            payment.save()

            return JsonResponse({'success': True})
        except Payment.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Payment không tồn tại'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Phương thức không hợp lệ'})

def revenue_pie_data(request):
    now = timezone.localtime(timezone.now())
    today = now.date()
    current_month = today.month
    current_year = today.year

    data = (
        Payment.objects
        .filter(
            status='paid',
            paid_at__year=current_year,
            paid_at__month=current_month
        )
        .values(title=F('fee__title'))
        .annotate(total=Sum('fee__amount'))
    )

    total_amount = sum(item['total'] for item in data)
    response_data = [
        {
            'title': item['title'],
            'value': round(item['total'] / total_amount * 100, 1) if total_amount > 0 else 0
        } for item in data
    ]

    return JsonResponse(response_data, safe=False)

@csrf_exempt
def login_view(request):
    
    if request.method == 'GET':
        return render(request, 'dangnhap.html')

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            username = data.get('username')
            password = data.get('password')
            role_input = data.get('role')

            role_map = {
                'resident': 'chu_ho',
                'leader': ['to_truong', 'to_pho'],
                'accountant': 'thu_ky'
            }
            allowed_roles = role_map.get(role_input)
            if isinstance(allowed_roles, str):
                allowed_roles = [allowed_roles]

            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT user_id, username, fullname, role
                    FROM users
                    WHERE username = %s
                    AND role IN %s
                    AND password_hash = crypt(%s, password_hash)
                    AND status = 'active'
                """, [username, tuple(allowed_roles), password])
                row = cursor.fetchone()

            if row:
                # ✔️ Lưu trạng thái đăng nhập
                request.session['user_id'] = str(row[0])
                request.session['username'] = row[1]
                request.session['fullname'] = row[2]
                request.session['role'] = row[3]

                return JsonResponse({
                    'success': True,
                    'redirect_url': get_redirect_url(row[3]),
                    'user': {'fullname': row[2], 'username': row[1], 'role': row[3]}
                })
            else:
                return JsonResponse({'success': False, 'message': 'Sai tài khoản, mật khẩu hoặc vai trò không hợp lệ.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': 'Chỉ hỗ trợ POST'})

def logout_view(request):
    request.session.flush()  
    return redirect('/login')

def get_redirect_url(role):
    if role == 'chu_ho':
        return '/cudan'
    elif role in ['to_truong', 'to_pho']:
        return '/admin'
    elif role == 'thu_ky':
        return '/ketoan'
    return '/login'

urlpatterns = [
    path('login/', login_view, name='home'), 
    path('logout/', logout_view, name='logout'),  
    path('admin/', admin.site.urls),
    path('ketoan/', ketoan_view, name='ketoan'),
    path('cudan/', homeowner_view, name='cudan'),
    path('update_payment/', update_payment, name='update_payment'),
    path('revenue_pie_data/', revenue_pie_data, name='revenue_pie_data'),
]

