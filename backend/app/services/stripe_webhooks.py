"""
Stripe Webhook Event Handlers
Handles all Stripe webhook events for subscriptions, payments, and disputes
"""

import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ============================================================================
# WEBHOOK EVENT HANDLERS
# ============================================================================

async def handle_webhook_event(
    db: AsyncSession,
    event_type: str,
    data: dict
) -> None:
    """Route webhook events to appropriate handlers"""
    
    handlers = {
        "customer.created": handle_customer_created,
        "customer.updated": handle_customer_updated,
        "customer.deleted": handle_customer_deleted,
        "customer.subscription.created": handle_subscription_created,
        "customer.subscription.updated": handle_subscription_updated,
        "customer.subscription.deleted": handle_subscription_deleted,
        "invoice.created": handle_invoice_created,
        "invoice.finalized": handle_invoice_finalized,
        "invoice.paid": handle_invoice_paid,
        "invoice.payment_failed": handle_invoice_payment_failed,
        "charge.succeeded": handle_charge_succeeded,
        "charge.failed": handle_charge_failed,
        "payment_intent.succeeded": handle_payment_intent_succeeded,
        "payment_intent.payment_failed": handle_payment_intent_payment_failed,
    }
    
    handler = handlers.get(event_type)
    if handler:
        try:
            await handler(db, data)
        except Exception as e:
            logger.error(f"Error handling webhook {event_type}: {e}")
            # Store failed event for retry
            await store_failed_event(db, event_type, data, str(e))
    else:
        logger.warning(f"No handler for event type: {event_type}")

async def store_failed_event(
    db: AsyncSession,
    event_type: str,
    event_data: dict,
    error_message: str
) -> None:
    """Store failed webhook event for manual review and retry"""
    try:
        org_id = event_data.get("metadata", {}).get("org_id")
        
        insert_query = text("""
            INSERT INTO billing_events (
              org_id, event_type, event_payload,
              is_error, error_message
            ) VALUES (
              :org_id, :event_type, :payload,
              true, :error_message
            )
        """)
        
        await db.execute(insert_query, {
            "org_id": org_id,
            "event_type": event_type,
            "payload": event_data,
            "error_message": error_message
        })
        
        await db.commit()
        logger.info(f"Stored failed event: {event_type}")
        
    except Exception as e:
        logger.error(f"Error storing failed event: {e}")

# ============================================================================
# CUSTOMER EVENTS
# ============================================================================

async def handle_customer_created(db: AsyncSession, data: dict) -> None:
    """Handle customer creation"""
    try:
        customer_id = data.get("id")
        org_id = data.get("metadata", {}).get("org_id")
        
        if not org_id:
            logger.warning(f"No org_id in customer metadata: {customer_id}")
            return
        
        logger.info(f"Customer created: {customer_id} for org {org_id}")
        
    except Exception as e:
        logger.error(f"Error handling customer creation: {e}")
        raise

async def handle_customer_updated(db: AsyncSession, data: dict) -> None:
    """Handle customer updates"""
    try:
        customer_id = data.get("id")
        logger.info(f"Customer updated: {customer_id}")
        
    except Exception as e:
        logger.error(f"Error handling customer update: {e}")
        raise

async def handle_customer_deleted(db: AsyncSession, data: dict) -> None:
    """Handle customer deletion"""
    try:
        customer_id = data.get("id")
        logger.info(f"Customer deleted: {customer_id}")
        
    except Exception as e:
        logger.error(f"Error handling customer deletion: {e}")
        raise

# ============================================================================
# SUBSCRIPTION EVENTS
# ============================================================================

async def handle_subscription_created(db: AsyncSession, data: dict) -> None:
    """Handle subscription creation"""
    try:
        subscription_id = data.get("id")
        customer_id = data.get("customer")
        tier_name = data.get("metadata", {}).get("tier")
        
        # Get org from customer
        query = text("""
            SELECT id FROM organizations 
            WHERE stripe_customer_id = :customer_id
            LIMIT 1
        """)
        result = await db.execute(query, {"customer_id": customer_id})
        org_id = result.scalar()
        
        if not org_id:
            logger.warning(f"No org found for customer {customer_id}")
            return
        
        # Parse subscription details
        status = data.get("status")
        current_period_start = datetime.fromtimestamp(data.get("current_period_start", 0))
        current_period_end = datetime.fromtimestamp(data.get("current_period_end", 0))
        trial_start = data.get("trial_start")
        trial_end = data.get("trial_end")
        
        amount_paid = data.get("items", {}).get("data", [{}])[0].get("price", {}).get("unit_amount", 0)
        billing_interval = data.get("items", {}).get("data", [{}])[0].get("price", {}).get("recurring", {}).get("interval", "month")
        
        # Insert subscription
        insert_query = text("""
            INSERT INTO subscriptions (
              org_id, stripe_subscription_id, tier_name,
              amount_paid, billing_interval, status,
              started_at, current_period_start, current_period_end,
              trial_start, trial_end
            ) VALUES (
              :org_id, :subscription_id, :tier,
              :amount, :interval, :status,
              NOW(), :period_start, :period_end,
              :trial_start, :trial_end
            )
            ON CONFLICT (stripe_subscription_id) DO UPDATE SET
              status = :status,
              current_period_start = :period_start,
              current_period_end = :period_end
        """)
        
        await db.execute(insert_query, {
            "org_id": org_id,
            "subscription_id": subscription_id,
            "tier": tier_name,
            "amount": amount_paid,
            "interval": billing_interval,
            "status": status,
            "period_start": current_period_start,
            "period_end": current_period_end,
            "trial_start": datetime.fromtimestamp(trial_start) if trial_start else None,
            "trial_end": datetime.fromtimestamp(trial_end) if trial_end else None
        })
        
        # Update organization tier
        update_query = text("""
            UPDATE organizations
            SET 
              tier_name = :tier,
              subscription_status = :status,
              billing_cycle_start = :period_start,
              billing_cycle_end = :period_end,
              stripe_subscription_id = :subscription_id,
              updated_at = NOW()
            WHERE id = :org_id
        """)
        
        await db.execute(update_query, {
            "org_id": org_id,
            "tier": tier_name,
            "status": status,
            "period_start": current_period_start,
            "period_end": current_period_end,
            "subscription_id": subscription_id
        })
        
        await db.commit()
        logger.info(f"Subscription created: {subscription_id} for org {org_id}")
        
    except Exception as e:
        logger.error(f"Error handling subscription creation: {e}")
        raise

async def handle_subscription_updated(db: AsyncSession, data: dict) -> None:
    """Handle subscription updates"""
    try:
        subscription_id = data.get("id")
        status = data.get("status")
        
        # Update subscription
        update_query = text("""
            UPDATE subscriptions
            SET 
              status = :status,
              current_period_start = :period_start,
              current_period_end = :period_end,
              cancel_at_period_end = :cancel_at_period_end,
              updated_at = NOW()
            WHERE stripe_subscription_id = :subscription_id
        """)
        
        current_period_start = datetime.fromtimestamp(data.get("current_period_start", 0))
        current_period_end = datetime.fromtimestamp(data.get("current_period_end", 0))
        
        await db.execute(update_query, {
            "subscription_id": subscription_id,
            "status": status,
            "period_start": current_period_start,
            "period_end": current_period_end,
            "cancel_at_period_end": data.get("cancel_at_period_end", False)
        })
        
        # Update organization status
        org_query = text("""
            UPDATE organizations
            SET 
              subscription_status = :status,
              billing_cycle_start = :period_start,
              billing_cycle_end = :period_end,
              cancel_at_period_end = :cancel_at_period_end,
              updated_at = NOW()
            WHERE stripe_subscription_id = :subscription_id
        """)
        
        await db.execute(org_query, {
            "subscription_id": subscription_id,
            "status": status,
            "period_start": current_period_start,
            "period_end": current_period_end,
            "cancel_at_period_end": data.get("cancel_at_period_end", False)
        })
        
        await db.commit()
        logger.info(f"Subscription updated: {subscription_id}, status: {status}")
        
    except Exception as e:
        logger.error(f"Error handling subscription update: {e}")
        raise

async def handle_subscription_deleted(db: AsyncSession, data: dict) -> None:
    """Handle subscription cancellation"""
    try:
        subscription_id = data.get("id")
        
        # Update subscription as canceled
        update_query = text("""
            UPDATE subscriptions
            SET 
              status = 'canceled',
              canceled_at = NOW(),
              updated_at = NOW()
            WHERE stripe_subscription_id = :subscription_id
        """)
        
        await db.execute(update_query, {"subscription_id": subscription_id})
        
        # Update organization
        org_query = text("""
            UPDATE organizations
            SET 
              subscription_status = 'canceled',
              tier_name = 'free_trial',
              updated_at = NOW()
            WHERE stripe_subscription_id = :subscription_id
        """)
        
        await db.execute(org_query, {"subscription_id": subscription_id})
        
        await db.commit()
        logger.info(f"Subscription deleted/canceled: {subscription_id}")
        
    except Exception as e:
        logger.error(f"Error handling subscription deletion: {e}")
        raise

# ============================================================================
# INVOICE EVENTS
# ============================================================================

async def handle_invoice_created(db: AsyncSession, data: dict) -> None:
    """Handle invoice creation"""
    try:
        invoice_id = data.get("id")
        customer_id = data.get("customer")
        
        # Get org from customer
        query = text("""
            SELECT id FROM organizations 
            WHERE stripe_customer_id = :customer_id
            LIMIT 1
        """)
        result = await db.execute(query, {"customer_id": customer_id})
        org_id = result.scalar()
        
        # Store invoice
        amount_total = data.get("total", 0)
        issue_date = datetime.fromtimestamp(data.get("created", 0))
        
        insert_query = text("""
            INSERT INTO invoices (
              org_id, stripe_invoice_id, amount_total,
              currency, issue_date, status,
              hosted_invoice_url, pdf_url
            ) VALUES (
              :org_id, :invoice_id, :amount,
              :currency, :issue_date, :status,
              :hosted_url, :pdf_url
            )
            ON CONFLICT (stripe_invoice_id) DO NOTHING
        """)
        
        await db.execute(insert_query, {
            "org_id": org_id,
            "invoice_id": invoice_id,
            "amount": amount_total,
            "currency": data.get("currency", "usd"),
            "issue_date": issue_date,
            "status": data.get("status", "draft"),
            "hosted_url": data.get("hosted_invoice_url"),
            "pdf_url": data.get("invoice_pdf")
        })
        
        await db.commit()
        logger.info(f"Invoice created: {invoice_id}")
        
    except Exception as e:
        logger.error(f"Error handling invoice creation: {e}")
        raise

async def handle_invoice_finalized(db: AsyncSession, data: dict) -> None:
    """Handle invoice finalization"""
    try:
        invoice_id = data.get("id")
        logger.info(f"Invoice finalized: {invoice_id}")
        
    except Exception as e:
        logger.error(f"Error handling invoice finalization: {e}")
        raise

async def handle_invoice_paid(db: AsyncSession, data: dict) -> None:
    """Handle invoice payment"""
    try:
        invoice_id = data.get("id")
        amount_paid = data.get("amount_paid", 0)
        paid_date = datetime.fromtimestamp(data.get("status_transitions", {}).get("paid_at", 0))
        
        update_query = text("""
            UPDATE invoices
            SET 
              status = 'paid',
              amount_paid = :amount,
              paid_date = :paid_date,
              updated_at = NOW()
            WHERE stripe_invoice_id = :invoice_id
        """)
        
        await db.execute(update_query, {
            "invoice_id": invoice_id,
            "amount": amount_paid,
            "paid_date": paid_date
        })
        
        await db.commit()
        logger.info(f"Invoice paid: {invoice_id}, amount: ${amount_paid/100:.2f}")
        
    except Exception as e:
        logger.error(f"Error handling invoice payment: {e}")
        raise

async def handle_invoice_payment_failed(db: AsyncSession, data: dict) -> None:
    """Handle failed invoice payment"""
    try:
        invoice_id = data.get("id")
        logger.warning(f"Invoice payment failed: {invoice_id}")
        
        update_query = text("""
            UPDATE invoices
            SET status = 'open'
            WHERE stripe_invoice_id = :invoice_id
        """)
        
        await db.execute(update_query, {"invoice_id": invoice_id})
        await db.commit()
        
    except Exception as e:
        logger.error(f"Error handling invoice payment failure: {e}")
        raise

# ============================================================================
# CHARGE & PAYMENT INTENT EVENTS
# ============================================================================

async def handle_charge_succeeded(db: AsyncSession, data: dict) -> None:
    """Handle successful charge"""
    try:
        charge_id = data.get("id")
        customer_id = data.get("customer")
        amount = data.get("amount", 0)
        
        logger.info(f"Charge succeeded: {charge_id}, customer: {customer_id}, amount: ${amount/100:.2f}")
        
    except Exception as e:
        logger.error(f"Error handling charge success: {e}")
        raise

async def handle_charge_failed(db: AsyncSession, data: dict) -> None:
    """Handle failed charge"""
    try:
        charge_id = data.get("id")
        failure_message = data.get("failure_message", "Unknown error")
        
        logger.warning(f"Charge failed: {charge_id}, reason: {failure_message}")
        
    except Exception as e:
        logger.error(f"Error handling charge failure: {e}")
        raise

async def handle_payment_intent_succeeded(db: AsyncSession, data: dict) -> None:
    """Handle successful payment intent"""
    try:
        intent_id = data.get("id")
        customer_id = data.get("customer")
        amount = data.get("amount", 0)
        metadata = data.get("metadata", {})
        
        # If this is a credit purchase, add credits to org
        if metadata.get("type") == "credit_purchase":
            org_id = metadata.get("org_id")
            num_credits = int(metadata.get("num_credits", 0))
            
            if org_id and num_credits > 0:
                # Get current balance
                balance_query = text("""
                    SELECT COALESCE(SUM(CASE WHEN transaction_type = 'usage' THEN -amount ELSE amount END), 0)::INT as balance
                    FROM ai_credits_ledger
                    WHERE org_id = :org_id
                """)
                
                result = await db.execute(balance_query, {"org_id": org_id})
                balance = result.scalar() or 0
                new_balance = balance + num_credits
                
                # Add to ledger
                ledger_query = text("""
                    INSERT INTO ai_credits_ledger (
                      org_id, transaction_type, amount,
                      description, balance_after
                    ) VALUES (
                      :org_id, 'purchase', :amount,
                      'Credit purchase via Stripe payment intent',
                      :balance
                    )
                """)
                
                await db.execute(ledger_query, {
                    "org_id": org_id,
                    "amount": num_credits,
                    "balance": new_balance
                })
                
                await db.commit()
                logger.info(f"Added {num_credits} credits to org {org_id}")
        
        logger.info(f"Payment intent succeeded: {intent_id}, amount: ${amount/100:.2f}")
        
    except Exception as e:
        logger.error(f"Error handling payment intent success: {e}")
        raise

async def handle_payment_intent_payment_failed(db: AsyncSession, data: dict) -> None:
    """Handle failed payment intent"""
    try:
        intent_id = data.get("id")
        last_error = data.get("last_payment_error", {})
        failure_message = last_error.get("message", "Unknown error")
        
        logger.warning(f"Payment intent failed: {intent_id}, reason: {failure_message}")
        
    except Exception as e:
        logger.error(f"Error handling payment intent failure: {e}")
        raise
