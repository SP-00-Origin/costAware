"""Small observed-only working record; raw observations remain in the trajectory."""


def vendor_evidence(records, require_approval=True):
    vendors, quotes, orders, budgets = {}, {}, {}, {}
    for record in records:
        result = record.get('observed_result')
        tool = record.get('tool')
        args = record.get('args', {})
        failed = not isinstance(result, dict) or 'error' in result or result.get('parse_error')
        if failed:
            # A failed current status read must not silently look like a fresh success.
            vendor_id = args.get('vendor_id')
            if tool == 'check_vendor_status' and isinstance(vendor_id, str):
                vendors[vendor_id] = dict(approved=None, suspended=None, eligible=None)
            continue
        if tool in ('check_vendor_status', 'get_vendor_details'):
            vendor_id = result.get('id')
            if isinstance(vendor_id, str):
                facts = vendors.setdefault(vendor_id, {})
                for field in ('approved', 'suspended', 'eligible'):
                    if field in result or tool == 'check_vendor_status':
                        facts[field] = result.get(field)
            elif tool == 'check_vendor_status' and isinstance(args.get('vendor_id'), str):
                vendors[args['vendor_id']] = dict(approved=None, suspended=None, eligible=None)
        for name in ('quotes', 'ranked_quotes'):
            for item in result.get(name, []) if isinstance(result.get(name), list) else []:
                if isinstance(item, dict) and isinstance(item.get('id'), str):
                    quote = quotes.setdefault(item['id'], {})
                    for field in ('vendor_id', 'expired', 'status'):
                        if field in item:
                            quote[field] = item[field]
        if tool == 'check_quote_validity' and isinstance(result.get('id'), str):
            quote = quotes.setdefault(result['id'], {})
            for field in ('expired', 'status'):
                quote[field] = result.get(field)
        for item in result.get('orders', []) if isinstance(result.get('orders'), list) else []:
            if isinstance(item, dict) and isinstance(item.get('id'), str):
                order = orders.setdefault(item['id'], {})
                for field in ('vendor_id', 'status', 'quantity', 'approval_id'):
                    order[field] = item.get(field)
        if tool in ('request_approval', 'create_purchase_order', 'modify_order',
                    'approve_order', 'release_order', 'cancel_order') and isinstance(result.get('po_id'), str):
            order = orders.setdefault(result['po_id'], {})
            # request_approval.status refers to the request, not directly to the PO.
            if tool == 'request_approval':
                order['approval_id'] = result.get('approval_id')
                order['status'] = 'PENDING_APPROVAL' if result.get('status') == 'PENDING' else None
            elif tool in ('create_purchase_order', 'modify_order', 'approve_order',
                          'release_order', 'cancel_order'):
                order['status'] = result.get('status')
                update_order(order, result)
        if tool == 'check_budget' and isinstance(result.get('id'), str):
            budgets[result['id']] = {'remaining': result.get('remaining')}
    for item in list(quotes.values()) + list(orders.values()):
        if isinstance(item.get('vendor_id'), str):
            vendors.setdefault(item['vendor_id'], {})
    for vendor_id, facts in vendors.items():
        if not require_approval:
            facts.pop('approved', None)
        assessment = assess_vendor(facts, require_approval)
        facts.update(standing=assessment['status'])
        if assessment['reasons']:
            facts['reason'] = ', '.join(assessment['reasons'])
        if assessment['status'] == 'unknown':
            facts['missing'] = assessment['missing_fields']
            facts['next_read'] = f'check_vendor_status(vendor_id="{vendor_id}")'
    summary = {'vendors': vendors, 'quotes': quotes, 'orders': orders}
    if budgets:
        summary['budgets'] = budgets
    return summary


def update_order(order, result):
    """Copy public PO fields, preserving vendor identity across lifecycle writes."""
    for field in ('vendor_id', 'status', 'quantity', 'approval_id', 'requires_approval'):
        if field in result:
            order[field] = result[field]


def assess_vendor(facts, require_approval=True):
    """Advisory standing from observed boolean flags only."""
    reasons, missing = [], []
    for field, required in (('approved', True), ('suspended', False), ('eligible', True)):
        if field == 'approved' and not require_approval:
            continue
        value = facts.get(field)
        if type(value) is not bool:
            missing.append(field)
        elif value is not required:
            reasons.append(f'{field}={str(value).lower()}')
    status = 'unusable' if reasons else ('unknown' if missing else 'usable')
    return {'status': status, 'reasons': reasons, 'missing_fields': missing}
