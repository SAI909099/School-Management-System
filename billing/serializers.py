from rest_framework import serializers
from academics.models import Student
from .models import TuitionPlan, Invoice, Payment

class TuitionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = TuitionPlan
        fields = ('id', 'clazz', 'amount_uzs')

# billing/serializers.py
class InvoiceSerializer(serializers.ModelSerializer):
    total_due_uzs = serializers.SerializerMethodField()
    balance_uzs = serializers.SerializerMethodField()
    # NEW:
    cumulative_balance_uzs = serializers.SerializerMethodField()
    prepaid_uzs = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = (
            'id','student','month','amount_uzs','discount_uzs','penalty_uzs',
            'paid_uzs','status','due_date','notes',
            'total_due_uzs','balance_uzs',
            # NEW:
            'cumulative_balance_uzs','prepaid_uzs'
        )
        read_only_fields = ('paid_uzs','status')

    def get_total_due_uzs(self, obj):
        return int(obj.total_due_uzs)

    def get_balance_uzs(self, obj):
        return int(obj.balance_uzs)

    def get_cumulative_balance_uzs(self, obj):
        # context: cum_balances is a dict {(student_id, month_iso): int_balance}
        m = getattr(self, 'context', {}).get('cum_balances', {})
        key = (obj.student_id, obj.month.isoformat())
        val = m.get(key)
        return int(val) if val is not None else None

    def get_prepaid_uzs(self, obj):
        cum = self.get_cumulative_balance_uzs(obj)
        if cum is None:
            return None
        # if cumulative is negative, that’s prepaid
        return abs(cum) if cum < 0 else 0


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ('id','student','invoice','amount_uzs','method','paid_at','receipt_no','note')

    def validate(self, data):
        inv = data.get('invoice')
        if not inv:
            raise serializers.ValidationError('invoice is required')
        if inv.student_id != data.get('student').id:
            raise serializers.ValidationError('student does not match invoice.student')
        if data.get('amount_uzs', 0) <= 0:
            raise serializers.ValidationError('amount_uzs must be > 0')
        return data

# billing/serializers.py (append)
# billing/serializers.py
from rest_framework import serializers
from .models import Expense

class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = ('id','date','amount_uzs','method','category','reason','created_by','created_at')
        read_only_fields = ('id','created_by','created_at')

    def create(self, validated_data):
        # created_by from request.user
        request = self.context.get('request')
        if request and request.user and not validated_data.get('created_by'):
            validated_data['created_by'] = request.user
        return super().create(validated_data)

