from landlord.models.bill import Bill as PydanticBill
from landlord.models.bill import BillLineItem as PydanticBillLineItem
from landlord.models.billing import Billing as PydanticBilling
from landlord.models.billing import BillingItem as PydanticBillingItem

from . import models


def to_pydantic_billing(db_billing: models.Billing) -> PydanticBilling:
    items = [
        PydanticBillingItem(
            id=item.id,
            billing_id=item.billing_id,
            description=item.description,
            amount=item.amount,
            item_type=item.item_type,
            sort_order=item.sort_order,
        )
        for item in db_billing.items.all()
    ]
    return PydanticBilling(
        id=db_billing.id,
        uuid=db_billing.uuid,
        name=db_billing.name,
        description=db_billing.description,
        pix_key=db_billing.pix_key,
        items=items,
        created_at=db_billing.created_at,
        updated_at=db_billing.updated_at,
        deleted_at=db_billing.deleted_at,
    )


def to_pydantic_bill(db_bill: models.Bill) -> PydanticBill:
    line_items = [
        PydanticBillLineItem(
            id=item.id,
            bill_id=item.bill_id,
            description=item.description,
            amount=item.amount,
            item_type=item.item_type,
            sort_order=item.sort_order,
        )
        for item in db_bill.line_items.all()
    ]
    return PydanticBill(
        id=db_bill.id,
        uuid=db_bill.uuid,
        billing_id=db_bill.billing_id,
        reference_month=db_bill.reference_month,
        total_amount=db_bill.total_amount,
        line_items=line_items,
        pdf_path=db_bill.pdf_path,
        notes=db_bill.notes,
        due_date=db_bill.due_date,
        created_at=db_bill.created_at,
    )
