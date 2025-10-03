# billing/views.py

from datetime import date, timedelta
from django.db import transaction
from django.db.models import Sum, Q, F
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import Student, SchoolClass
from .models import TuitionPlan, Invoice, Payment, SalaryPayout
from .serializers import TuitionPlanSerializer, InvoiceSerializer, PaymentSerializer, ExpenseSerializer
from .permissions import IsAdminOrAccountantWrite
from .utils import month_first, parse_month


# =========================
# Tuition Plans
# =========================

class TuitionPlanViewSet(viewsets.ModelViewSet):
    queryset = TuitionPlan.objects.select_related('clazz').all()
    serializer_class = TuitionPlanSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrAccountantWrite]

    @action(detail=False, methods=['post'], url_path='bulk-set')
    def bulk_set(self, request):
        """
        POST /api/billing/plans/bulk-set/
        Body:
          {
            "all": true,                # optional; if false, pass class_ids
            "class_ids": [1,2,3],       # optional if 'all' is true
            "amount_uzs": 450000,       # required, > 0
            "only_missing": false       # optional; if true, do NOT overwrite existing plans
          }
        """
        role = getattr(request.user, 'role', '')
        if role not in ('admin', 'accountant'):
            return Response({'detail': 'Forbidden'}, status=403)

        try:
            amount = int(request.data.get('amount_uzs', 0))
        except Exception:
            return Response({'detail': 'amount_uzs must be integer'}, status=400)
        if amount <= 0:
            return Response({'detail': 'amount_uzs must be > 0'}, status=400)

        only_missing = bool(request.data.get('only_missing', False))
        class_ids = request.data.get('class_ids')
        if request.data.get('all') or not class_ids:
            class_ids = list(SchoolClass.objects.values_list('id', flat=True))

        created, updated = 0, 0
        with transaction.atomic():
            for cid in class_ids:
                plan, was_created = TuitionPlan.objects.get_or_create(
                    clazz_id=cid,
                    defaults={'amount_uzs': amount}
                )
                if was_created:
                    created += 1
                else:
                    if only_missing:
                        continue
                    if plan.amount_uzs != amount:
                        plan.amount_uzs = amount
                        plan.save(update_fields=['amount_uzs'])
                        updated += 1

        return Response({'ok': True, 'created': created, 'updated': updated, 'count': len(class_ids)})


# =========================
# Invoices
# =========================

class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.select_related('student', 'student__clazz').all()
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrAccountantWrite]

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        # Role scoping
        if getattr(u, 'role', None) == 'parent':
            child_ids = u.children_links.values_list('student_id', flat=True)
            qs = qs.filter(student_id__in=child_ids)
        elif getattr(u, 'role', None) == 'teacher':
            try:
                t = u.teacher_profile
                qs = qs.filter(Q(student__clazz__class_teacher=t) | Q(student__clazz__schedule__teacher=t))
            except Exception:
                qs = qs.none()
        # Filters
        month = self.request.query_params.get('month')  # YYYY-MM
        clazz = self.request.query_params.get('class')
        status_f = self.request.query_params.get('status')
        if month:
            qs = qs.filter(month=parse_month(month))
        if clazz:
            qs = qs.filter(student__clazz_id=clazz)
        if status_f:
            qs = qs.filter(status=status_f)
        return qs.distinct()

    @action(detail=False, methods=['post'])
    def generate(self, request):
        """
        Generate monthly invoices for all active students (optionally filter by class).
        Query params: month=YYYY-MM, class=<id>, due_day=10, default_amount=<int>
        """
        if getattr(request.user, 'role', None) not in ('admin', 'accountant'):
            return Response({'detail': 'Forbidden'}, status=403)

        m = request.query_params.get('month')
        if not m:
            return Response({'detail': 'month=YYYY-MM required'}, status=400)
        month_dt = parse_month(m)
        class_id = request.query_params.get('class')
        due_day = int(request.query_params.get('due_day', 10))
        default_amount = int(request.query_params.get('default_amount', 0))

        students = Student.objects.filter(status='active')
        if class_id:
            students = students.filter(clazz_id=class_id)

        created, updated = 0, 0
        for s in students.select_related('clazz'):
            plan = getattr(s.clazz, 'tuition_plan', None)
            amt = plan.amount_uzs if plan else default_amount
            inv, was_created = Invoice.objects.get_or_create(
                student=s, month=month_dt,
                defaults={
                    'amount_uzs': amt,
                    'discount_uzs': 0,
                    'penalty_uzs': 0,
                    'paid_uzs': 0,
                    'status': 'unpaid',
                    'due_date': month_dt.replace(day=min(due_day, 28))
                }
            )
            if was_created:
                created += 1
            else:
                if inv.amount_uzs != amt and amt:
                    inv.amount_uzs = amt
                    inv.recompute_status()
                    inv.save()
                    updated += 1
        return Response({'ok': True, 'created': created, 'updated': updated})

    @action(detail=False, methods=['get'])
    def overdue(self, request):
        """List overdue invoices: status != paid AND due_date < today. Optional: month=YYYY-MM, class."""
        qs = self.get_queryset()
        today = date.today()
        qs = qs.filter(~Q(status='paid'), due_date__lt=today)
        month = self.request.query_params.get('month')
        if month:
            qs = qs.filter(month=parse_month(month))
        return Response(self.serializer_class(qs, many=True).data)

    @action(detail=True, methods=['post'])
    def recompute(self, request, pk=None):
        inv = self.get_object()
        inv.recompute_status()
        inv.save(update_fields=['status'])
        return Response(self.serializer_class(inv).data)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        # If DRF has already serialized, we need to rebuild with context to include cumulative balances.
        # Easier approach: override to build data ourselves:

        qs = self.filter_queryset(self.get_queryset())
        month_str = request.query_params.get('month')  # YYYY-MM
        serializer_context = self.get_serializer_context()

        if month_str:
            month_dt = parse_month(month_str)
            # Build cumulative balances up to the filtered month for each invoice's student
            # (total_due - paid) for all invoices where month <= filtered month
            from collections import defaultdict
            cum_by_student = defaultdict(int)

            # prefetch all relevant invoices (for performance, limit to involved students)
            student_ids = list(qs.values_list('student_id', flat=True).distinct())
            all_up_to = Invoice.objects.filter(
                student_id__in=student_ids,
                month__lte=month_dt
            ).values('student_id', 'month', 'amount_uzs', 'discount_uzs', 'penalty_uzs', 'paid_uzs').order_by(
                'student_id', 'month')

            # We’ll compute cumulative for each month and store only the value at the filtered month
            cum_at_month = {}
            for row in all_up_to:
                sid = row['student_id']
                due = (row['amount_uzs'] - row['discount_uzs'] + row['penalty_uzs'])
                paid = row['paid_uzs']
                cum_by_student[sid] += int(due) - int(paid)

            # For the serializer to show it per invoice (in that month),
            # map (student, month_filtered) -> cum_balance
            cum_balances = {(sid, month_dt.isoformat()): bal for sid, bal in cum_by_student.items()}
            serializer_context['cum_balances'] = cum_balances

            ser = self.get_serializer(qs, many=True, context=serializer_context)
            return Response(ser.data)

        # No month filter: just return default
        return Response(self.get_serializer(qs, many=True, context=serializer_context).data)


# =========================
# Payments
# =========================

# billing/views.py (add imports near the top)
from decimal import Decimal
from django.utils.timezone import now as tz_now
from .utils import parse_month, next_month
from .models import TuitionPlan, Invoice, Payment

class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.select_related('invoice', 'student', 'student__clazz').all()
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrAccountantWrite]

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        if getattr(u, 'role', None) == 'parent':
            child_ids = u.children_links.values_list('student_id', flat=True)
            qs = qs.filter(student_id__in=child_ids)
        elif getattr(u, 'role', None) == 'teacher':
            try:
                t = u.teacher_profile
                qs = qs.filter(Q(student__clazz__class_teacher=t) | Q(student__clazz__schedule__teacher=t))
            except Exception:
                qs = qs.none()
        month = self.request.query_params.get('month')
        if month:
            qs = qs.filter(invoice__month=parse_month(month))
        student = self.request.query_params.get('student')
        if student:
            qs = qs.filter(student_id=student)
        return qs.distinct()

    # NEW: split/allocate surplus of a payment to future months
    def create(self, request, *args, **kwargs):
        # Validate & create the primary payment normally
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = serializer.save()  # this updates invoice.paid_uzs via Payment.save()

        inv = payment.invoice
        student = payment.student
        remaining = Decimal(payment.amount_uzs)

        # How much of this payment was actually needed for the current invoice?
        inv.refresh_from_db()
        needed_here = inv.total_due_uzs - (inv.paid_uzs - payment.amount_uzs)
        if needed_here < 0:
            needed_here = Decimal(0)

        # Surplus after covering the current invoice
        surplus = remaining - needed_here
        # If “payment” itself pushed invoice into negative (rare edge), clamp
        if surplus < 0:
            surplus = Decimal(0)

        # If there is surplus, allocate it forward month-by-month
        if surplus > 0:
            # figure per-month tuition amount
            plan_amt = None
            plan = getattr(student.clazz, 'tuition_plan', None) if getattr(student, 'clazz', None) else None
            if plan:
                plan_amt = Decimal(plan.amount_uzs)

            cur_month = inv.month
            # start from the NEXT month
            m = next_month(cur_month)

            # Keep allocating until surplus is gone
            # Safety cap (24 months) to avoid infinite loops if data is odd
            for _ in range(24):
                if surplus <= 0:
                    break

                # ensure invoice exists for month m
                next_inv, _c = Invoice.objects.get_or_create(
                    student=student,
                    month=m,
                    defaults={
                        'amount_uzs': plan_amt or inv.amount_uzs,   # fallback to current-month amount
                        'discount_uzs': 0,
                        'penalty_uzs': 0,
                        'paid_uzs': 0,
                        'status': 'unpaid',
                        'due_date': m.replace(day=min(10, 28)),     # default due day; tweak if needed
                        'notes': 'Auto-created by overpayment allocation'
                    }
                )

                # how much still needed for that month
                next_inv.refresh_from_db()
                need = next_inv.total_due_uzs - next_inv.paid_uzs
                if need <= 0:
                    # already fully paid (perhaps from a previous allocation) → move to the next month
                    m = next_month(m)
                    continue

                allocate = surplus if surplus <= need else need

                # create a child payment for that next invoice
                Payment.objects.create(
                    student=student,
                    invoice=next_inv,
                    amount_uzs=allocate,
                    method=payment.method,
                    paid_at=payment.paid_at or tz_now(),
                    receipt_no=payment.receipt_no,
                    note=f"Auto-alloc from {inv.month.strftime('%Y-%m')}"
                )
                surplus -= allocate

                # move to the next month after trying this one
                if surplus > 0:
                    m = next_month(m)

        headers = self.get_success_headers(serializer.data)
        return Response(self.get_serializer(payment).data, status=status.HTTP_201_CREATED, headers=headers)



# =========================
# Student Billing (per-student quick endpoints)
# =========================

class StudentBillingViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def _can_view(self, request, student_id: int) -> bool:
        u = request.user
        if getattr(u, 'role', None) in ('admin', 'accountant', 'registrar', 'teacher'):
            return True
        if getattr(u, 'role', None) == 'parent':
            return u.children_links.filter(student_id=student_id).exists()
        return False

    @action(detail=False, methods=['get'], url_path='(?P<student_id>[^/.]+)/balance')
    def balance(self, request, student_id=None):
        if not self._can_view(request, student_id):
            return Response({'detail': 'Forbidden'}, status=403)
        inv = Invoice.objects.filter(student_id=student_id)
        totals = inv.aggregate(
            total_due=Sum(F('amount_uzs') - F('discount_uzs') + F('penalty_uzs')),
            total_paid=Sum('paid_uzs')
        )
        total_due = int(totals['total_due'] or 0)
        total_paid = int(totals['total_paid'] or 0)
        return Response({
            'student': int(student_id),
            'total_due_uzs': total_due,
            'total_paid_uzs': total_paid,
            'balance_uzs': total_due - total_paid
        })

    @action(detail=False, methods=['get'], url_path='(?P<student_id>[^/.]+)/invoices')
    def invoices(self, request, student_id=None):
        if not self._can_view(request, student_id):
            return Response({'detail': 'Forbidden'}, status=403)
        qs = Invoice.objects.filter(student_id=student_id).order_by('-month')
        return Response(InvoiceSerializer(qs, many=True).data)

    @action(detail=False, methods=['get'], url_path='(?P<student_id>[^/.]+)/payments')
    def payments(self, request, student_id=None):
        if not self._can_view(request, student_id):
            return Response({'detail': 'Forbidden'}, status=403)
        qs = Payment.objects.filter(student_id=student_id).order_by('-paid_at')
        return Response(PaymentSerializer(qs, many=True).data)


# =========================
# Summary / Reports
# =========================

# billing/views.py  (REPLACE the last SummaryView with this one)

from datetime import date as _date, timedelta
from django.db.models import Sum, Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Payment, SalaryPayout  # ⬅ ensure SalaryPayout is imported
try:
    from .models import Expense
except Exception:
    Expense = None

class SummaryView(APIView):
    """
    GET /api/billing/summary/?from=YYYY-MM-DD&to=YYYY-MM-DD&include_salaries=1
    Response:
    {
      from, to,
      income, expense, balance, debtors_count,
      income_by_method: {cash, card, transfer},
      expense_by_method:{cash, card, transfer}   # salaries are counted into 'transfer'
    }
    """
    permission_classes = [IsAuthenticated]

    def _month_bounds(self, today: _date):
        first = today.replace(day=1)
        next_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
        last = next_month - timedelta(days=1)
        return first, last

    def get(self, request):
        # range
        f_str = request.query_params.get('from')
        t_str = request.query_params.get('to')
        if not (f_str and t_str):
            today = _date.today()
            first, last = self._month_bounds(today)
            f_str = f_str or first.isoformat()
            t_str = t_str or last.isoformat()

        # include salaries?
        inc_sal = request.query_params.get('include_salaries') in ('1', 'true', 'yes')

        # incomes (student payments)
        pay_qs = Payment.objects.filter(paid_at__date__gte=f_str, paid_at__date__lte=t_str)
        income_total = pay_qs.aggregate(total=Sum('amount_uzs'))['total'] or 0
        income_by_method = {'cash': 0, 'card': 0, 'transfer': 0}
        for m, _ in getattr(Payment, 'METHOD', (('cash','Naqd'), ('card','Karta'), ('transfer','O‘tkazma'))):
            income_by_method[m] = pay_qs.filter(method=m).aggregate(total=Sum('amount_uzs'))['total'] or 0

        # expenses = manual expenses (+ salaries if requested)
        expense_total = 0
        expense_by_method = {'cash': 0, 'card': 0, 'transfer': 0}

        # 1) Manual expenses
        if Expense is not None:
            ex_qs = Expense.objects.filter(date__gte=f_str, date__lte=t_str)
            expense_total += ex_qs.aggregate(total=Sum('amount_uzs'))['total'] or 0
            for m, _ in getattr(Expense, 'METHOD', (('cash','Naqd'), ('card','Karta'), ('transfer','O‘tkazma'))):
                expense_by_method[m] += ex_qs.filter(method=m).aggregate(total=Sum('amount_uzs'))['total'] or 0

        # 2) Salaries (paid only) — count as 'transfer' by default
        if inc_sal:
            sal_qs = SalaryPayout.objects.filter(paid=True)
            # date window: use paid_at.date if exists, else the month (first day)
            sal_qs = sal_qs.filter(
                Q(paid_at__date__gte=f_str, paid_at__date__lte=t_str) |
                Q(paid_at__isnull=True, month__gte=f_str, month__lte=t_str)
            )

            sal_sum = sal_qs.aggregate(total=Sum('amount_uzs'))['total'] or 0
            expense_total += sal_sum
            expense_by_method['transfer'] += sal_sum  # map salaries into 'transfer' bucket

        # optional: real debtors_count
        debtors_count = 0
        try:
            from .models import Invoice
            debtors_count = Invoice.objects.filter(~Q(status='paid')).values('student').distinct().count()
        except Exception:
            pass

        balance = int(income_total) - int(expense_total)

        return Response({
            'from': f_str,
            'to': t_str,
            'income': int(income_total),
            'expense': int(expense_total),
            'balance': int(balance),
            'debtors_count': int(debtors_count),
            'income_by_method': {k: int(v or 0) for k, v in income_by_method.items()},
            'expense_by_method': {k: int(v or 0) for k, v in expense_by_method.items()},
        })


class PaymentsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        t = request.query_params.get('type', 'income')
        # TODO.txt: replace with queryset results
        if t == 'income':
            data = [
                {"id": 1, "date": str(date.today()), "amount": 1000000, "payer_name": "Test.T"},
                {"id": 2, "date": str(date.today()), "amount": 900000, "payer_name": "Test.T"},
            ]
        else:
            data = [
                {"id": 10, "date": str(date.today()), "amount": 500000, "reason": "Ofis sarfi"},
                {"id": 11, "date": str(date.today()), "amount": 200000, "reason": "Kantselyariya"},
            ]
        return Response(data)


class DebtorsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # TODO.txt: replace with real debt query
        data = [
            {"student_id": 1, "student_name": "Ali Aliyev", "class_name": "7-A", "parent_phone": "+998901112233", "debt": 150000},
            {"student_id": 2, "student_name": "Dilnoza Karimova", "class_name": "7-A", "parent_phone": "+998909998877", "debt": 200000},
        ]
        return Response(data)


# =========================
# Salaries (optional, for /moliya/oylik/)
# =========================

class SalariesListView(APIView):
    """
    GET /api/billing/salaries/?month=YYYY-MM
    Returns: [{fio, date, paid}, ...]
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        m = request.query_params.get('month')
        if not m:
            m = date.today().strftime('%Y-%m')
        mdt = parse_month(m)
        rows = SalaryPayout.objects.filter(month=mdt).order_by('fio', 'date')
        data = [{'fio': r.fio, 'date': r.date.isoformat(), 'paid': bool(r.paid)} for r in rows]
        return Response(data)


class SalariesMarkView(APIView):
    """
    POST /api/billing/salaries/mark/
    body: {"month": "YYYY-MM", "items": [{"fio": "...", "date": "YYYY-MM-DD", "paid": true}, ...]}
    Upserts rows by (month, fio, date).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        role = getattr(request.user, 'role', '')
        if role not in ('admin', 'accountant'):
            return Response({'detail': 'Forbidden'}, status=403)

        m = (request.data.get('month') or '').strip()
        items = request.data.get('items') or []
        if not m:
            return Response({'detail': 'month required (YYYY-MM)'}, status=400)
        try:
            mdt = parse_month(m)
        except Exception:
            return Response({'detail': 'invalid month format'}, status=400)

        created = 0
        updated = 0
        for it in items:
            fio = (it.get('fio') or '').strip()
            dt = it.get('date')
            paid = bool(it.get('paid'))
            if not fio or not dt:
                continue
            try:
                y, mo, d = map(int, dt.split('-'))
                from datetime import date as _d
                dtx = _d(y, mo, d)
            except Exception:
                continue

            obj, was_created = SalaryPayout.objects.update_or_create(
                month=mdt, fio=fio, date=dtx,
                defaults={'paid': paid}
            )
            created += 1 if was_created else 0
            updated += 0 if was_created else 1

        return Response({'ok': True, 'created': created, 'updated': updated})


# billing/views.py  (add imports at top)
from django.utils import timezone
from accounts.models import User
from academics.models import Teacher
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import SalaryPayout, SalaryMonthLock
from .utils import parse_month


# ---- STAFF LIST FOR A MONTH ----
class SalariesStaffView(APIView):
    """
    GET /api/billing/salaries/staff/?month=YYYY-MM
    Returns:
    {
      "locked": true|false,
      "items":[
        {"user": 12, "full_name":"...", "role":"teacher", "specialty":"Matematika", "amount_uzs": 0, "paid": false}
      ]
    }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        m = request.query_params.get('month')
        if not m:
            from datetime import date
            m = date.today().strftime('%Y-%m')
        month_dt = parse_month(m)

        locked = SalaryMonthLock.objects.filter(month=month_dt).exists()

        # Which roles to include in salaries page:
        roles = ('teacher', 'accountant', 'registrar', 'operator', 'admin')
        staff = list(User.objects.filter(role__in=roles).order_by('last_name', 'first_name'))

        # Map teacher -> specialty
        teachers = {t.user_id: t for t in Teacher.objects.select_related('specialty')}
        # Prefetch existing payouts
        existing = {
            (sp.user_id): sp
            for sp in SalaryPayout.objects.filter(month=month_dt, user_id__in=[u.id for u in staff])
        }

        items = []
        for u in staff:
            full = f"{(u.first_name or '').strip()} {(u.last_name or '').strip()}".strip() or (
                        getattr(u, 'phone', '') or str(u))
            specialty = ""
            if u.role == 'teacher':
                t = teachers.get(u.id)
                specialty = t.specialty.name if (t and t.specialty) else ""
            sp = existing.get(u.id)
            items.append({
                "user": u.id,
                "full_name": full,
                "role": u.role or "",
                "specialty": specialty,
                "amount_uzs": int(sp.amount_uzs) if sp else 0,
                "paid": bool(sp.paid) if sp else False,
            })

        return Response({"locked": locked, "items": items})


# ---- SAVE / UPSERT SALARIES FOR A MONTH ----
class SalariesMarkView(APIView):
    """
    POST /api/billing/salaries/mark/
    {
      "month": "YYYY-MM",
      "items":[{"user":12,"amount_uzs":450000,"paid":true}, ...]
    }
    Block if month is locked.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        role = getattr(request.user, 'role', '')
        if role not in ('admin', 'accountant'):
            return Response({'detail': 'Forbidden'}, status=403)

        m = (request.data.get('month') or '').strip()
        items = request.data.get('items') or []
        if not m:
            return Response({'detail': 'month required (YYYY-MM)'}, status=400)
        try:
            month_dt = parse_month(m)
        except Exception:
            return Response({'detail': 'invalid month format'}, status=400)

        # Check lock
        if SalaryMonthLock.objects.filter(month=month_dt).exists():
            return Response({'detail': 'This month is locked'}, status=400)

        created = 0
        updated = 0
        for it in items:
            uid = it.get('user')
            amt = int(it.get('amount_uzs') or 0)
            paid = bool(it.get('paid'))
            if not uid:
                continue
            obj, was_created = SalaryPayout.objects.get_or_create(
                month=month_dt, user_id=uid,
                defaults={'amount_uzs': amt, 'paid': paid, 'paid_at': timezone.now() if paid else None}
            )
            if was_created:
                created += 1
            else:
                obj.amount_uzs = amt
                # keep paid_at if already paid; set if changing to paid
                if paid and not obj.paid:
                    obj.paid_at = timezone.now()
                obj.paid = paid
                obj.save(update_fields=['amount_uzs', 'paid', 'paid_at'])
                updated += 1

        return Response({'ok': True, 'created': created, 'updated': updated})


# ---- FINALIZE / LOCK MONTH ----
class SalariesFinalizeView(APIView):
    """
    POST /api/billing/salaries/finalize/
    {"month":"YYYY-MM"}
    Creates a lock to prevent further edits.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        role = getattr(request.user, 'role', '')
        if role not in ('admin', 'accountant'):
            return Response({'detail': 'Forbidden'}, status=403)

        m = (request.data.get('month') or '').strip()
        if not m:
            return Response({'detail': 'month required'}, status=400)
        try:
            month_dt = parse_month(m)
        except Exception:
            return Response({'detail': 'invalid month format'}, status=400)

        if SalaryMonthLock.objects.filter(month=month_dt).exists():
            return Response({'detail': 'Already locked'}, status=400)

        SalaryMonthLock.objects.create(month=month_dt, locked_by=request.user)
        return Response({'ok': True, 'locked': True})

# billing/views.py
from django.utils.dateparse import parse_date
from django.db.models import Sum
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import Payment, SalaryPayout, SalaryMonthLock

# billing/views.py (replace PaymentsView)
class PaymentsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        t = (request.query_params.get('type') or 'income').lower()
        from_str = request.query_params.get('from')
        to_str = request.query_params.get('to')
        inc_sal = request.query_params.get('include_salaries') in ('1', 'true', 'yes')

        dfrom = parse_date(from_str) if from_str else None
        dto   = parse_date(to_str) if to_str else None

        if t == 'income':
            qs = Payment.objects.all().select_related('student')
            if dfrom: qs = qs.filter(paid_at__date__gte=dfrom)
            if dto:   qs = qs.filter(paid_at__date__lte=dto)
            data = [{
                "id": p.id,
                "date": p.paid_at.date().isoformat(),
                "amount": int(p.amount_uzs),
                "method": p.method,
                "reason": f"Talaba to‘lovi — {p.student}",  # adjust if you want full name formatting
                "kind": "income",
            } for p in qs]
            return Response(data)

        # Expense = manual expenses + salaries (optional) + lock rollups (optional)
        rows = []

        # 1) Manual expenses
        ex_qs = Expense.objects.all()
        if dfrom: ex_qs = ex_qs.filter(date__gte=dfrom)
        if dto:   ex_qs = ex_qs.filter(date__lte=dto)
        for e in ex_qs:
            rows.append({
                "id": f"exp-{e.id}",
                "date": e.date.isoformat(),
                "amount": int(e.amount_uzs),
                "method": e.method or "-",
                "reason": e.reason or e.get_category_display(),
                "kind": "manual",
                "category": e.category,
                "category_name": e.get_category_display(),
            })

        # 2) Salaries (if asked)
        if inc_sal:
            qs = SalaryPayout.objects.filter(paid=True).select_related('user')
            if dfrom: qs = qs.filter(paid_at__date__gte=dfrom)
            if dto:   qs = qs.filter(paid_at__date__lte=dto)
            for s in qs:
                full = f"{(s.user.first_name or '').strip()} {(s.user.last_name or '').strip()}".strip() or getattr(s.user, 'phone', '')
                rows.append({
                    "id": f"sal-{s.id}",
                    "date": s.paid_at.date().isoformat() if s.paid_at else s.month.isoformat(),
                    "amount": int(s.amount_uzs),
                    "method": "salary",
                    "reason": f"Oylik — {full}",
                    "kind": "salary",
                })

            locks = SalaryMonthLock.objects.all()
            if dfrom:
                locks = locks.filter(month__gte=dfrom.replace(day=1))
            if dto:
                locks = locks.filter(month__lte=dto.replace(day=1))
            for lock in locks:
                total = SalaryPayout.objects.filter(month=lock.month, paid=True).aggregate(s=Sum('amount_uzs'))['s'] or 0
                rows.append({
                    "id": f"lock-{lock.id}",
                    "date": lock.locked_at.date().isoformat(),
                    "amount": int(total),
                    "method": "—",
                    "reason": f"Oyliklar yakuni — {lock.month.strftime('%Y-%m')}",
                    "kind": "salary_total",
                })

        # sort by date ASC before returning (UI also sorts but this helps)
        rows.sort(key=lambda r: r.get('date') or '')
        return Response(rows)


# billing/views.py (append imports)
# billing/views.py
from django.db.models import Q
from rest_framework import viewsets, permissions
from .models import Expense
from .serializers import ExpenseSerializer
from .permissions import IsAdminOrAccountantWrite

class ExpenseViewSet(viewsets.ModelViewSet):
    queryset = Expense.objects.all().order_by('-date','-id')
    serializer_class = ExpenseSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrAccountantWrite]

    def get_queryset(self):
        qs = super().get_queryset()
        qp = self.request.query_params

        f = qp.get('from')      # YYYY-MM-DD
        t = qp.get('to')        # YYYY-MM-DD
        q = qp.get('q')         # text search
        method = qp.get('method')
        category = qp.get('category')

        if f: qs = qs.filter(date__gte=f)
        if t: qs = qs.filter(date__lte=t)
        if method: qs = qs.filter(method=method)
        if category: qs = qs.filter(category=category)
        if q:
            qs = qs.filter(
                Q(reason__icontains=q) |
                Q(method__icontains=q) |
                Q(category__icontains=q)
            )
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


# billing/views.py
from datetime import date as _date, timedelta
from django.db.models import Sum, Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Payment
try:
    from .models import Expense  # your manual expense model
except Exception:
    Expense = None  # allow code to run while model is being added

class SummaryView(APIView):
    """
    GET /api/billing/summary/?from=YYYY-MM-DD&to=YYYY-MM-DD
    Response:
    {
      from, to,
      income, expense, balance, debtors_count,
      income_by_method: {cash, card, transfer},
      expense_by_method:{cash, card, transfer}
    }
    """
    permission_classes = [IsAuthenticated]

    def _month_bounds(self, today: _date):
        first = today.replace(day=1)
        next_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
        last = next_month - timedelta(days=1)
        return first, last

    def get(self, request):
        # range
        f_str = request.query_params.get('from')
        t_str = request.query_params.get('to')

        if not (f_str and t_str):
            today = _date.today()
            first, last = self._month_bounds(today)
            f_str = f_str or first.isoformat()
            t_str = t_str or last.isoformat()

        # incomes
        pay_qs = Payment.objects.filter(paid_at__date__gte=f_str, paid_at__date__lte=t_str)
        income_total = pay_qs.aggregate(total=Sum('amount_uzs'))['total'] or 0
        income_by_method = {}
        for m, _ in getattr(Payment, 'METHOD', (('cash','Naqd'), ('card','Karta'), ('transfer','O‘tkazma'))):
            income_by_method[m] = pay_qs.filter(method=m).aggregate(total=Sum('amount_uzs'))['total'] or 0

        # expenses
        expense_total = 0
        expense_by_method = {'cash': 0, 'card': 0, 'transfer': 0}
        if Expense is not None:
            ex_qs = Expense.objects.filter(date__gte=f_str, date__lte=t_str)
            expense_total = ex_qs.aggregate(total=Sum('amount_uzs'))['total'] or 0
            for m, _ in getattr(Expense, 'METHOD', (('cash','Naqd'), ('card','Karta'), ('transfer','O‘tkazma'))):
                expense_by_method[m] = ex_qs.filter(method=m).aggregate(total=Sum('amount_uzs'))['total'] or 0

        # optional: real debtors_count (keep placeholder if not implemented)
        debtors_count = 0
        try:
            from .models import Invoice
            debtors_count = Invoice.objects.filter(~Q(status='paid')).values('student').distinct().count()
        except Exception:
            pass

        balance = int(income_total) - int(expense_total)

        return Response({
            'from': f_str,
            'to': t_str,
            'income': int(income_total),
            'expense': int(expense_total),
            'balance': int(balance),
            'debtors_count': int(debtors_count),
            'income_by_method': {k: int(v or 0) for k, v in income_by_method.items()},
            'expense_by_method': {k: int(v or 0) for k, v in expense_by_method.items()},
        })

