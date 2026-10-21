import TransactionPage from '../TransactionPage'

const COPY = {
  noun: 'expense',
  formTitle: 'New entry',
  placeholder: 'What was it for?',
  empty: 'Nothing recorded for this month.',
}

export default function Expenses() {
  return <TransactionPage type="expense" copy={COPY} />
}
