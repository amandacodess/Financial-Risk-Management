import TransactionPage from '../TransactionPage'

const COPY = {
  noun: 'income entry',
  formTitle: 'What came in',
  placeholder: 'Anything worth remembering',
  empty: 'Nothing recorded for this month. Add what came in and Savings can show what share of it you kept.',
}

export default function Income() {
  return <TransactionPage type="income" copy={COPY} />
}
