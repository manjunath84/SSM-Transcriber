// Pure presentational budget pill.
//
// 7a scope: STATIC render of the user's configured monthly budget from
// their profile. NO usage accounting / Gate-3 spend math — that is 7d.

interface BudgetPillProps {
  email: string;
  monthlyBudgetUsd: number;
}

function BudgetPill({ email, monthlyBudgetUsd }: BudgetPillProps) {
  return (
    <span className="budget-pill" title={email}>
      Budget: ${monthlyBudgetUsd}/mo
    </span>
  );
}

export default BudgetPill;
