"""The Holded API v2 endpoint catalog.

Single source of truth for the client and the CLI. Endpoints are grouped into
:class:`~pyholded._registry.Resource` objects by functional module. Resource
names are snake_case Python identifiers; the URL path segments (kebab-case, as
used by the v2 API) are written explicitly in each endpoint's path.

Base URL: ``https://api.holded.com/api/v2/`` — every path below is relative to it.
Authentication: ``Authorization: Bearer <token>`` (handled by the transport layer).
List endpoints are cursor-paginated and return ``{items, cursor, has_more}``.
"""

from __future__ import annotations

from ._registry import Endpoint, Resource

# v2 list endpoints are cursor-paginated.
_LIST_QUERY = ("limit", "cursor", "page")


def _crud(
    module: str,
    name: str,
    segment: str,
    *,
    id_param: str = "id",
    list_query: tuple[str, ...] = _LIST_QUERY,
    extra: tuple[Endpoint, ...] = (),
) -> Resource:
    """Build a standard list/get/create/update/delete resource."""
    item = f"{segment}/{{{id_param}}}"
    endpoints = (
        Endpoint("list", "GET", segment, f"List {name}.", query_params=list_query),
        Endpoint("get", "GET", item, f"Get a single {name} record."),
        Endpoint("create", "POST", segment, f"Create a {name} record.", has_body=True),
        Endpoint("update", "PUT", item, f"Update a {name} record.", has_body=True),
        Endpoint("delete", "DELETE", item, f"Delete a {name} record."),
        *extra,
    )
    return Resource(
        module=module, name=name, description=f"{name} ({segment}).", endpoints=endpoints
    )


def _document(segment: str, singular: str) -> Resource:
    """Build a sales/purchase document resource: CRUD + pdf/pay/send actions.

    The resource name is the plural path ``segment`` (snake-cased); ``singular``
    is only used to phrase the help text.
    """
    name = segment.replace("-", "_")
    item = f"{segment}/{{id}}"
    return Resource(
        module="invoicing",
        name=name,
        description=f"{singular.title()}s ({segment}).",
        endpoints=(
            Endpoint("list", "GET", segment, f"List {segment}.", query_params=_LIST_QUERY),
            Endpoint("get", "GET", item, f"Get a {singular}."),
            Endpoint("create", "POST", segment, f"Create a {singular}.", has_body=True),
            Endpoint("update", "PUT", item, f"Update a {singular}.", has_body=True),
            Endpoint("delete", "DELETE", item, f"Delete a {singular}."),
            Endpoint("getPdf", "GET", f"{item}/pdf", f"Download the {singular} PDF.", binary=True),
            Endpoint(
                "pay", "POST", f"{item}/pay", f"Register a payment on a {singular}.", has_body=True
            ),
            Endpoint("send", "POST", f"{item}/send", f"Send a {singular} by email.", has_body=True),
        ),
    )


# --------------------------------------------------------------------------- #
# Sales & purchase documents
# --------------------------------------------------------------------------- #

invoices = _document("invoices", "invoice")
credit_notes = _document("credit-notes", "credit note")
sales_orders = _document("sales-orders", "sales order")
estimates = _document("estimates", "estimate")
proformas = _document("proformas", "proforma")
waybills = _document("waybills", "waybill")
sales_receipts = _document("sales-receipts", "sales receipt")
purchases = _document("purchases", "purchase")
purchase_orders = _document("purchase-orders", "purchase order")

# --------------------------------------------------------------------------- #
# Invoicing — masters
# --------------------------------------------------------------------------- #

contacts = _crud("invoicing", "contacts", "contacts")
contact_groups = _crud("invoicing", "contact_groups", "contact-groups")
products = _crud("invoicing", "products", "products")
services = _crud("invoicing", "services", "services")
warehouses = _crud("invoicing", "warehouses", "warehouses")
payments = _crud("invoicing", "payments", "payments")
sales_channels = _crud("invoicing", "sales_channels", "sales-channels")
expenses_accounts = _crud("invoicing", "expenses_accounts", "expenses-accounts")

taxes = Resource(
    module="invoicing",
    name="taxes",
    description="Tax definitions (taxes).",
    endpoints=(
        Endpoint("list", "GET", "taxes", "List taxes.", query_params=_LIST_QUERY),
        Endpoint("get", "GET", "taxes/{id}", "Get a tax."),
    ),
)

payment_methods = Resource(
    module="invoicing",
    name="payment_methods",
    description="Payment methods (payment-methods).",
    endpoints=(
        Endpoint(
            "list", "GET", "payment-methods", "List payment methods.", query_params=_LIST_QUERY
        ),
        Endpoint("get", "GET", "payment-methods/{id}", "Get a payment method."),
    ),
)

# --------------------------------------------------------------------------- #
# CRM
# --------------------------------------------------------------------------- #

funnels = _crud("crm", "funnels", "funnels")
events = _crud("crm", "events", "events")
leads = _crud(
    "crm",
    "leads",
    "leads",
    extra=(
        Endpoint("createNote", "POST", "leads/{id}/notes", "Add a note to a lead.", has_body=True),
        Endpoint("createTask", "POST", "leads/{id}/tasks", "Add a task to a lead.", has_body=True),
    ),
)

bookings = Resource(
    module="crm",
    name="bookings",
    description="Bookings (bookings).",
    endpoints=(
        Endpoint("list", "GET", "bookings", "List bookings.", query_params=_LIST_QUERY),
        Endpoint("get", "GET", "bookings/{id}", "Get a booking."),
    ),
)

booking_locations = Resource(
    module="crm",
    name="booking_locations",
    description="Booking locations (booking-locations).",
    endpoints=(
        Endpoint(
            "list", "GET", "booking-locations", "List booking locations.", query_params=_LIST_QUERY
        ),
    ),
)

# --------------------------------------------------------------------------- #
# Projects
# --------------------------------------------------------------------------- #

projects = _crud("projects", "projects", "projects")
tasks = _crud("projects", "tasks", "tasks")

# --------------------------------------------------------------------------- #
# Team / HR
# --------------------------------------------------------------------------- #

employees = _crud("team", "employees", "employees")


REGISTRY: tuple[Resource, ...] = (
    # documents
    invoices,
    credit_notes,
    sales_orders,
    estimates,
    proformas,
    waybills,
    sales_receipts,
    purchases,
    purchase_orders,
    # invoicing masters
    contacts,
    contact_groups,
    products,
    services,
    warehouses,
    payments,
    payment_methods,
    sales_channels,
    expenses_accounts,
    taxes,
    # crm
    funnels,
    leads,
    events,
    bookings,
    booking_locations,
    # projects
    projects,
    tasks,
    # team
    employees,
)
