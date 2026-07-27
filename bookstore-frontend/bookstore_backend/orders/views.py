import json
import uuid
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Sum
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Order, OrderItem, Payment, Payout, PayoutRequest, SupportMessage, SiteSettings
from .serializers import (
    OrderSerializer, PaymentSerializer, PayoutSerializer,
    PayoutRequestSerializer, SupportMessageSerializer, SiteSettingsSerializer,
)
from books.models import Book


def _chapa_api_request(path, method='POST', payload=None):
    url = f"{settings.CHAPA_BASE_URL.rstrip('/')}{path}"
    body = None
    if payload is not None:
        body = json.dumps(payload).encode('utf-8')

    request = Request(
        url,
        data=body,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {settings.CHAPA_SECRET_KEY}',
        },
        method=method,
    )

    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode('utf-8'))
    except HTTPError as exc:
        payload = exc.read().decode('utf-8')
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return {'status': False, 'message': payload}
    except URLError as exc:
        return {'status': False, 'message': str(exc)}


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or getattr(user, 'role', '').upper() == 'ADMIN':
            return Order.objects.all().order_by('-created_at')
        elif getattr(user, 'role', '').upper() == 'MERCHANT':
            return Order.objects.filter(items__book__merchant=user).distinct().order_by('-created_at')
        return Order.objects.filter(user=user).order_by('-created_at')

    def partial_update(self, request, *args, **kwargs):
        """Role-based status updates: merchant only."""
        user = request.user
        role = getattr(user, 'role', '').upper()
        order = self.get_object()
        new_status = request.data.get('status')

        if not new_status:
            serializer = self.get_serializer(order)
            return Response(serializer.data)

        # Admin cannot change order status
        if role == 'ADMIN' or user.is_superuser:
            return Response({'error': 'Admin cannot change order status.'}, status=status.HTTP_403_FORBIDDEN)

        # Merchant transitions
        if role == 'MERCHANT':
            allowed = {
                'PAID': ['SHIPPED'],
                'SHIPPED': ['DELIVERED'],
            }
            if order.status not in allowed or new_status not in allowed.get(order.status, []):
                return Response(
                    {'error': f'Merchant can only: PAID→SHIPPED, SHIPPED→DELIVERED. Current: {order.status}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            order.status = new_status
            if new_status == 'DELIVERED':
                order.delivered_at = timezone.now()
            order.save()

            # Create payout record when delivered
            if new_status == 'DELIVERED':
                self._create_payout(order)

            serializer = self.get_serializer(order)
            return Response(serializer.data)

        # Regular user — no status changes via PATCH (use /confirm/ or /dispute/ instead)
        return Response({'error': 'Use /confirm/ or /dispute/ actions.'}, status=status.HTTP_403_FORBIDDEN)

    def _create_payout(self, order):
        """Create a pending payout when order is delivered."""
        from decimal import Decimal
        # Find the merchant(s) for this order's books
        merchants = set()
        for item in order.items.all():
            merchants.add(item.book.merchant)

        for merchant in merchants:
            # Calculate this merchant's portion
            merchant_items = order.items.filter(book__merchant=merchant)
            merchant_amount = sum(item.book.price * item.quantity for item in merchant_items)

            if not Payout.objects.filter(order=order, merchant=merchant).exists():
                commission_rate = Decimal('10.00')
                commission_amount = (merchant_amount * commission_rate / Decimal('100')).quantize(Decimal('0.01'))
                payout_amount = merchant_amount - commission_amount

                Payout.objects.create(
                    order=order,
                    merchant=merchant,
                    order_amount=merchant_amount,
                    commission_rate=commission_rate,
                    commission_amount=commission_amount,
                    payout_amount=payout_amount,
                    status='PENDING',
                )

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """User confirms delivery."""
        order = self.get_object()
        if order.user != request.user:
            return Response({'error': 'Only the buyer can confirm delivery.'}, status=status.HTTP_403_FORBIDDEN)
        if order.status != 'DELIVERED':
            return Response({'error': 'Order must be in DELIVERED status to confirm.'}, status=status.HTTP_400_BAD_REQUEST)

        order.status = 'CONFIRMED'
        order.confirmed_at = timezone.now()
        order.save()

        serializer = self.get_serializer(order)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def dispute(self, request, pk=None):
        """User disputes delivery within 5-day window."""
        order = self.get_object()
        if order.user != request.user:
            return Response({'error': 'Only the buyer can dispute.'}, status=status.HTTP_403_FORBIDDEN)
        if order.status != 'DELIVERED':
            return Response({'error': 'Can only dispute orders marked as delivered.'}, status=status.HTTP_400_BAD_REQUEST)
        if order.is_deadline_passed:
            return Response({'error': 'The 5-day dispute window has passed.'}, status=status.HTTP_400_BAD_REQUEST)

        reason = request.data.get('reason', '')
        # For now, just hold the payout and keep status
        payouts = Payout.objects.filter(order=order, status='PENDING')
        payouts.update(status='HELD')
        return Response({'message': 'Dispute submitted. Payouts are on hold. Support will review.', 'reason': reason})


    def create(self, request, *args, **kwargs):
        items_data = request.data.get('items', [])
        shipping_address = request.data.get('shipping_address', '').strip()
        if not items_data:
            return Response({'error': 'No items provided'}, status=status.HTTP_400_BAD_REQUEST)
        if not shipping_address:
            return Response({'error': 'Shipping address is required'}, status=status.HTTP_400_BAD_REQUEST)

        total_amount = Decimal('0.00')
        order = Order.objects.create(user=request.user, total_amount=0)

        for item in items_data:
            try:
                book_id_int = int(item.get('book_id'))
            except (ValueError, TypeError):
                return Response({'error': f"Invalid book ID: {item.get('book_id')}. You cannot checkout with mock books."}, status=status.HTTP_400_BAD_REQUEST)
            book = get_object_or_404(Book, id=book_id_int, approved=True)
            quantity = max(1, int(item.get('quantity', 1)))
            OrderItem.objects.create(order=order, book=book, quantity=quantity)
            total_amount += book.price * quantity

        order.total_amount = total_amount
        order.save()

        tx_ref = f"bookstore-{request.user.id}-{uuid.uuid4().hex[:16]}"
        Payment.objects.create(
            order=order,
            tx_ref=tx_ref,
            address=shipping_address,
            payment_method=request.data.get('payment_method', 'CHAPA').upper(),
        )

        chapa_payload = {
            'amount': str(total_amount),
            'currency': 'ETB',
            'tx_ref': tx_ref,
            'return_url': f"{settings.CHAPA_RETURN_URL}?tx_ref={tx_ref}",
            'callback_url': settings.CHAPA_CALLBACK_URL,
            'customer_name': request.user.get_full_name() or request.user.username,
            'customer_email': request.user.email,
            'meta': {'order_id': order.id},
        }

        chapa_response = _chapa_api_request('/v1/transaction/initialize', payload=chapa_payload)
        chapa_data = chapa_response.get('data', {}) if isinstance(chapa_response, dict) else {}
        checkout_url = chapa_data.get('checkout_url') or chapa_data.get('authorization_url')

        if not chapa_response.get('status') or not checkout_url:
            order.status = 'FAILED'
            order.save()
            payment = order.payment
            payment.payment_status = 'FAILED'
            payment.save()
            return Response(
                {'error': 'Unable to initialize payment with Chapa', 'details': chapa_response},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {
                'checkout_url': checkout_url,
                'tx_ref': tx_ref,
                'order_id': order.id,
            },
            status=status.HTTP_201_CREATED,
        )


class ChapaPayView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        import traceback
        print(f"[ChapaPayView] ===== NEW REQUEST =====")
        print(f"[ChapaPayView] User: {request.user} (id={request.user.id})")
        print(f"[ChapaPayView] Raw data: {request.data}")
        print(f"[ChapaPayView] Content-Type: {request.content_type}")

        try:
            items_data = request.data.get('items', [])
            shipping_address = request.data.get('shipping_address', '').strip()
            print(f"[ChapaPayView] items_data={items_data}")
            print(f"[ChapaPayView] shipping_address={shipping_address}")

            if not items_data:
                book_id = request.data.get('book_id')
                if book_id:
                    items_data = [{'book_id': book_id, 'quantity': int(request.data.get('quantity', 1))}]

            if not items_data:
                print("[ChapaPayView] ERROR: No items provided")
                return Response({'error': 'No items provided'}, status=status.HTTP_400_BAD_REQUEST)
            if not shipping_address:
                print("[ChapaPayView] ERROR: No shipping address")
                return Response({'error': 'Shipping address is required'}, status=status.HTTP_400_BAD_REQUEST)

            total_amount = Decimal('0.00')
            order = Order.objects.create(user=request.user, total_amount=0)
            print(f"[ChapaPayView] Created order {order.id}")

            for item in items_data:
                print(f"[ChapaPayView] Processing item: {item}")
                try:
                    book_id_int = int(item.get('book_id'))
                except (ValueError, TypeError):
                    print(f"[ChapaPayView] ERROR: Invalid book_id: {item.get('book_id')}")
                    return Response({'error': f"Invalid book ID: {item.get('book_id')}. You cannot checkout with mock books."}, status=status.HTTP_400_BAD_REQUEST)
                
                book = Book.objects.filter(id=book_id_int, approved=True).first()
                if not book:
                    print(f"[ChapaPayView] ERROR: Book with id={book_id_int} not found or not approved")
                    # List available books for debugging
                    available = list(Book.objects.values_list('id', 'title', 'approved'))
                    print(f"[ChapaPayView] Available books: {available}")
                    return Response({
                        'error': f'Book with ID {book_id_int} not found or not approved.',
                        'available_book_ids': [b[0] for b in available],
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                quantity = max(1, int(item.get('quantity', 1)))
                OrderItem.objects.create(order=order, book=book, quantity=quantity)
                total_amount += book.price * quantity
                print(f"[ChapaPayView] Added book '{book.title}' x{quantity}, subtotal={book.price * quantity}")

            order.total_amount = total_amount
            order.save()
            print(f"[ChapaPayView] Order total: {total_amount}")

            tx_ref = f"bookstore-{request.user.id}-{uuid.uuid4().hex[:16]}"
            payment = Payment.objects.create(
                order=order,
                tx_ref=tx_ref,
                address=shipping_address,
                payment_method=request.data.get('payment_method', 'CHAPA').upper(),
            )
            print(f"[ChapaPayView] Created payment with tx_ref={tx_ref}")

            chapa_payload = {
                'amount': str(total_amount),
                'currency': 'ETB',
                'tx_ref': tx_ref,
                'return_url': f"{settings.CHAPA_RETURN_URL}?tx_ref={tx_ref}",
                'callback_url': settings.CHAPA_CALLBACK_URL,
                'customer_name': request.user.get_full_name() or request.user.username,
                'customer_email': request.user.email,
                'meta': {'order_id': order.id},
            }
            print(f"[ChapaPayView] Chapa payload: {chapa_payload}")
            print(f"[ChapaPayView] CHAPA_BASE_URL={settings.CHAPA_BASE_URL}")
            print(f"[ChapaPayView] CHAPA_SECRET_KEY={settings.CHAPA_SECRET_KEY[:20]}...")

            chapa_response = _chapa_api_request('/v1/transaction/initialize', payload=chapa_payload)
            print(f"[ChapaPayView] Chapa response: {chapa_response}")
            chapa_data = chapa_response.get('data', {}) if isinstance(chapa_response, dict) else {}
            checkout_url = chapa_data.get('checkout_url') or chapa_data.get('authorization_url')

            if not chapa_response.get('status') or not checkout_url:
                order.status = 'FAILED'
                order.save()
                payment.payment_status = 'FAILED'
                payment.save()
                print(f"[ChapaPayView] ERROR: Chapa initialization failed")
                return Response(
                    {'error': 'Unable to initialize payment with Chapa', 'details': chapa_response},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            print(f"[ChapaPayView] SUCCESS: checkout_url={checkout_url}")
            return Response(
                {
                    'checkout_url': checkout_url,
                    'tx_ref': tx_ref,
                    'order_id': order.id,
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            print(f"[ChapaPayView] UNHANDLED EXCEPTION: {e}")
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CheckoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        items_data = request.data.get('items', [])
        shipping_address = request.data.get('shipping_address', '').strip()
        if not items_data:
            return Response({'error': 'No items provided'}, status=status.HTTP_400_BAD_REQUEST)
        if not shipping_address:
            return Response({'error': 'Shipping address is required'}, status=status.HTTP_400_BAD_REQUEST)

        total_amount = Decimal('0.00')
        order = Order.objects.create(user=request.user, total_amount=0)

        for item in items_data:
            try:
                book_id_int = int(item.get('book_id'))
            except (ValueError, TypeError):
                return Response({'error': f"Invalid book ID: {item.get('book_id')}. You cannot checkout with mock books."}, status=status.HTTP_400_BAD_REQUEST)
            book = get_object_or_404(Book, id=book_id_int, approved=True)
            quantity = max(1, int(item.get('quantity', 1)))
            OrderItem.objects.create(order=order, book=book, quantity=quantity)
            total_amount += book.price * quantity

        order.total_amount = total_amount
        order.save()

        tx_ref = f"bookstore-{request.user.id}-{uuid.uuid4().hex[:16]}"
        payment = Payment.objects.create(
            order=order,
            tx_ref=tx_ref,
            address=shipping_address,
            payment_method=request.data.get('payment_method', 'CHAPA').upper(),
        )

        chapa_payload = {
            'amount': str(total_amount),
            'currency': 'ETB',
            'tx_ref': tx_ref,
            'return_url': f"{settings.CHAPA_RETURN_URL}?tx_ref={tx_ref}",
            'callback_url': settings.CHAPA_CALLBACK_URL,
            'customer_name': request.user.get_full_name() or request.user.username,
            'customer_email': request.user.email,
            'meta': {'order_id': order.id},
        }

        chapa_response = _chapa_api_request('/v1/transaction/initialize', payload=chapa_payload)
        chapa_data = chapa_response.get('data', {}) if isinstance(chapa_response, dict) else {}
        checkout_url = chapa_data.get('checkout_url') or chapa_data.get('authorization_url')

        if not chapa_response.get('status') or not checkout_url:
            order.status = 'FAILED'
            order.save()
            payment.payment_status = 'FAILED'
            payment.save()
            return Response(
                {'error': 'Unable to initialize payment with Chapa', 'details': chapa_response},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {
                'checkout_url': checkout_url,
                'tx_ref': tx_ref,
                'order_id': order.id,
            },
            status=status.HTTP_201_CREATED,
        )


class VerifyPaymentView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        tx_ref = request.query_params.get('tx_ref')
        if not tx_ref:
            return Response({'error': 'tx_ref query parameter is required'}, status=status.HTTP_400_BAD_REQUEST)

        chapa_response = _chapa_api_request(f'/v1/transaction/verify/{tx_ref}', method='GET')
        chapa_data = chapa_response.get('data', {}) if isinstance(chapa_response, dict) else {}
        transaction_status = chapa_data.get('status')
        reference = chapa_data.get('reference') or chapa_data.get('id')

        if not chapa_response.get('status'):
            return Response(
                {'error': 'Unable to verify payment with Chapa', 'details': chapa_response},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        payment = Payment.objects.filter(tx_ref=tx_ref).first()
        if payment:
            payment.chapa_reference = reference
            payment.payment_status = 'COMPLETED' if transaction_status == 'success' else 'FAILED'
            payment.save()

            order = payment.order
            order.status = 'PAID' if payment.payment_status == 'COMPLETED' else 'FAILED'
            order.save()

        return Response(
            {
                'status': 'PAID' if transaction_status == 'success' else 'FAILED',
                'transaction_id': reference,
                'tx_ref': tx_ref,
                'order_id': payment.order.id if payment else None,
            }
        )


class PaidOrdersView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        if user.is_superuser or getattr(user, 'role', '').upper() == 'ADMIN':
            queryset = Order.objects.filter(status='PAID').order_by('-created_at')
        elif getattr(user, 'role', '').upper() == 'MERCHANT':
            queryset = Order.objects.filter(items__book__merchant=user, status='PAID').distinct().order_by('-created_at')
        else:
            queryset = Order.objects.filter(user=user, status='PAID').order_by('-created_at')

        serializer = OrderSerializer(queryset, many=True)
        return Response(serializer.data)


class ChapaWebhookView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        tx_ref = request.data.get('tx_ref') or request.data.get('txRef')
        status_value = request.data.get('status')
        reference = request.data.get('reference') or request.data.get('transaction_reference')

        if not tx_ref:
            return Response({'detail': 'Missing tx_ref in webhook payload'}, status=status.HTTP_400_BAD_REQUEST)

        payment = Payment.objects.filter(tx_ref=tx_ref).first()
        if not payment:
            return Response({'detail': 'Payment record not found'}, status=status.HTTP_404_NOT_FOUND)

        if str(status_value).lower() == 'success':
            payment.payment_status = 'COMPLETED'
            payment.order.status = 'PAID'
        else:
            payment.payment_status = 'FAILED'
            payment.order.status = 'FAILED'

        if reference:
            payment.chapa_reference = reference

        payment.save()
        payment.order.save()

        return Response({'detail': 'Webhook processed successfully'})


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or getattr(user, 'role', '').upper() == 'ADMIN':
            return Payment.objects.all()
        elif getattr(user, 'role', '').upper() == 'MERCHANT':
            return Payment.objects.filter(order__items__book__merchant=user).distinct()
        return Payment.objects.filter(order__user=user)


class PayoutListView(APIView):
    """Admin: list all payouts."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        role = getattr(user, 'role', '').upper()

        if role == 'MERCHANT':
            payouts = Payout.objects.filter(merchant=user).order_by('-created_at')
        elif user.is_superuser or role == 'ADMIN':
            payouts = Payout.objects.all().order_by('-created_at')
        else:
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

        serializer = PayoutSerializer(payouts, many=True)
        return Response(serializer.data)


class PayoutReleaseView(APIView):
    """Admin: release a pending payout to merchant."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, payout_id, *args, **kwargs):
        user = request.user
        if not (user.is_superuser or getattr(user, 'role', '').upper() == 'ADMIN'):
            return Response({'error': 'Only admin can release payouts.'}, status=status.HTTP_403_FORBIDDEN)

        payout = get_object_or_404(Payout, id=payout_id)
        if payout.status == 'RELEASED':
            return Response({'error': 'Payout already released.'}, status=status.HTTP_400_BAD_REQUEST)
        if payout.status == 'HELD':
            return Response({'error': 'Payout is held due to a dispute.'}, status=status.HTTP_400_BAD_REQUEST)

        payout.status = 'RELEASED'
        payout.released_at = timezone.now()
        payout.save()

        serializer = PayoutSerializer(payout)
        return Response(serializer.data)


class AdminFinanceView(APIView):
    """Admin: financial dashboard stats."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        if not (user.is_superuser or getattr(user, 'role', '').upper() == 'ADMIN'):
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

        total_revenue = Order.objects.filter(
            status__in=['PAID', 'SHIPPED', 'DELIVERED', 'CONFIRMED']
        ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')

        all_payouts = Payout.objects.all()
        total_commission = all_payouts.aggregate(total=Sum('commission_amount'))['total'] or Decimal('0.00')
        total_payout_amount = all_payouts.aggregate(total=Sum('payout_amount'))['total'] or Decimal('0.00')

        pending_payouts = all_payouts.filter(status='PENDING')
        pending_amount = pending_payouts.aggregate(total=Sum('payout_amount'))['total'] or Decimal('0.00')

        released_payouts = all_payouts.filter(status='RELEASED')
        released_amount = released_payouts.aggregate(total=Sum('payout_amount'))['total'] or Decimal('0.00')

        held_payouts = all_payouts.filter(status='HELD')
        held_amount = held_payouts.aggregate(total=Sum('payout_amount'))['total'] or Decimal('0.00')

        return Response({
            'total_revenue': str(total_revenue),
            'total_commission': str(total_commission),
            'total_payout_amount': str(total_payout_amount),
            'pending_payout_count': pending_payouts.count(),
            'pending_payout_amount': str(pending_amount),
            'released_payout_count': released_payouts.count(),
            'released_payout_amount': str(released_amount),
            'held_payout_count': held_payouts.count(),
            'held_payout_amount': str(held_amount),
        })


class MerchantEarningsView(APIView):
    """Merchant: view own earnings summary."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        payouts = Payout.objects.filter(merchant=user)

        pending = payouts.filter(status='PENDING')
        released = payouts.filter(status='RELEASED')

        return Response({
            'pending_balance': str(pending.aggregate(total=Sum('payout_amount'))['total'] or Decimal('0.00')),
            'pending_count': pending.count(),
            'released_earnings': str(released.aggregate(total=Sum('payout_amount'))['total'] or Decimal('0.00')),
            'released_count': released.count(),
            'total_commission_paid': str(payouts.aggregate(total=Sum('commission_amount'))['total'] or Decimal('0.00')),
        })


# ─── Payout Requests (Merchant→Admin approval flow) ──────────

class PayoutRequestListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        role = getattr(user, 'role', '').upper()
        if user.is_superuser or role == 'ADMIN':
            qs = PayoutRequest.objects.all()
        elif role == 'MERCHANT':
            qs = PayoutRequest.objects.filter(merchant=user)
        else:
            return Response([], status=status.HTTP_200_OK)
        return Response(PayoutRequestSerializer(qs, many=True).data)

    def post(self, request):
        amount = request.data.get('amount')
        if not amount or float(amount) <= 0:
            return Response({'error': 'Invalid amount'}, status=status.HTTP_400_BAD_REQUEST)
        pr = PayoutRequest.objects.create(merchant=request.user, amount=amount)
        return Response(PayoutRequestSerializer(pr).data, status=status.HTTP_201_CREATED)


class PayoutRequestUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        user = request.user
        if not (user.is_superuser or getattr(user, 'role', '').upper() == 'ADMIN'):
            return Response({'error': 'Only admin can update payout requests.'}, status=status.HTTP_403_FORBIDDEN)
        pr = get_object_or_404(PayoutRequest, id=pk)
        new_status = request.data.get('status')
        if new_status in ['CONFIRMED', 'REJECTED']:
            pr.status = new_status
            pr.save()
        return Response(PayoutRequestSerializer(pr).data)


# ─── Support Messages (Merchant→Admin) ───────────────────────

class SupportMessageListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        role = getattr(user, 'role', '').upper()
        if user.is_superuser or role == 'ADMIN':
            qs = SupportMessage.objects.all()
        else:
            qs = SupportMessage.objects.filter(sender=user)
        return Response(SupportMessageSerializer(qs, many=True).data)

    def post(self, request):
        subject = request.data.get('subject', '').strip()
        message = request.data.get('message', '').strip()
        if not subject or not message:
            return Response({'error': 'Subject and message are required.'}, status=status.HTTP_400_BAD_REQUEST)
        msg = SupportMessage.objects.create(sender=request.user, subject=subject, message=message)
        return Response(SupportMessageSerializer(msg).data, status=status.HTTP_201_CREATED)


class SupportMessageUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        msg = get_object_or_404(SupportMessage, id=pk)
        if 'read' in request.data:
            msg.read = request.data['read']
            msg.save()
        return Response(SupportMessageSerializer(msg).data)


# ─── Site Settings ────────────────────────────────────────────

class SiteSettingsListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        settings_qs = SiteSettings.objects.all()
        result = {}
        for s in settings_qs:
            result[s.key] = s.value
        return Response(result)

    def put(self, request):
        user = request.user
        if not (user.is_authenticated and (user.is_superuser or getattr(user, 'role', '').upper() == 'ADMIN')):
            return Response({'error': 'Only admin can update settings.'}, status=status.HTTP_403_FORBIDDEN)
        for key, value in request.data.items():
            SiteSettings.objects.update_or_create(key=key, defaults={'value': str(value)})
        settings_qs = SiteSettings.objects.all()
        result = {s.key: s.value for s in settings_qs}
        return Response(result)
