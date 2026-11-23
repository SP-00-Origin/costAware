"""Explicit business-rule variants; the original task dataset is never rewritten."""
from .tasks import Task

VENDOR_RULES = ('qualified', 'suspension_only')


def vendor_rule_prompt(prompt, require_approval=True):
    if require_approval:
        return prompt
    prompt = prompt.replace('approved=true, suspended=false, eligible=true',
                            'suspended=false, eligible=true')
    return prompt + ('\nSupplier approval status is ignored in this variant. '
                     'Required purchase-order manager approval still applies.\n')


def vendor_rule_task(task: Task, rule='qualified') -> Task:
    if rule not in VENDOR_RULES:
        raise ValueError(f'Unknown vendor_rule: {rule}')
    if rule == 'qualified':
        return task
    task = task.model_copy(deep=True)
    task.expected_final_state['vendor_approval_required'] = False
    task.goal = task.goal.replace('approved and not suspended', 'eligible and not suspended')
    task.goal = task.goal.replace('suspended or not approved', 'suspended')
    task.goal += (' Supplier approval status does not restrict purchases in this variant. '
                  'Suspension and eligibility still apply, as does required purchase-order manager approval.')
    if task.id == 'T18':
        # V2 becomes the cheapest legal replacement when supplier approval is ignored.
        for requirement in task.expected_final_state['orders']:
            requirement['vendor_id'] = 'V2'
        for action in task.reference_solution:
            if action['tool'] == 'create_purchase_order':
                action['args']['quote_id'] = 'QY2'
        for negative in task.negatives:
            negative['name'] = 'suspended_replacement'
            for action in negative['trajectory']:
                if action['tool'] == 'create_purchase_order':
                    action['args']['quote_id'] = 'QY3'
    return task
