/** Explain-like-I'm-five tooltips for fundamentals & balance sheet line items. */
export const FUNDAMENTAL_TIPS = {
  pe: "Price divided by earnings per share. How many years of profits you'd pay for the company at today's price — higher can mean more expensive.",
  pb: "Price versus the company's book value (what it owns minus what it owes). Below 1 can mean you're paying less than the accounting value.",
  roe: "How much profit the company makes from its owners' equity. Like the return on the nest egg shareholders have in the business.",
  roa: "How much profit the company squeezes from everything it owns. Higher means assets are working harder.",
  gross_margin:
    "What's left from sales after paying for the product itself (before rent, ads, and salaries). Higher means each sale is fatter.",
  net_margin:
    "What's left as real profit after every cost and tax. The pennies kept from each dollar of sales.",
  debt_to_assets:
    "How much of what the company owns is funded by borrowing. Closer to 1 means more debt; closer to 0 means more equity-funded.",
  current_ratio:
    "Stuff that can turn into cash soon, divided by bills due soon. Above 1 means short-term bills look covered.",
  price: "Latest share price from our price history cache.",
  market_cap_approx:
    "Rough company size: share price × shares outstanding. How much the whole business would cost at today's price.",

  Cash: "Money in the bank the company can spend right away — like cash in a wallet.",
  ShortTermInvestments:
    "Money parked in things that can be sold quickly (like short-term bonds) — almost like cash, but earning a little.",
  AccountsReceivable:
    "IOUs from customers who bought something but haven't paid yet. Money the company is waiting to collect.",
  Inventory:
    "Stuff sitting on shelves or in warehouses waiting to be sold — toys in a toy store before someone buys them.",
  CurrentAssets:
    "All the things the company expects to use or turn into cash within about a year.",
  PropertyPlantEquipment:
    "Factories, buildings, machines, and equipment — the physical tools that help make and deliver products.",
  Goodwill:
    "Extra value from buying another company for more than its book assets — paying for brand, people, or know-how.",
  IntangibleAssets:
    "Valuable things you can't touch: patents, software, brands, licenses.",
  Assets:
    "Everything the company owns that has value — cash, factories, patents, and more. The whole toy box.",

  AccountsPayable:
    "Bills the company still owes to suppliers — like a tab at the store that hasn't been paid yet.",
  ShortTermDebt:
    "Borrowed money that must be paid back within about a year.",
  CurrentLiabilities:
    "All the bills and debts due within about a year.",
  LongTermDebt:
    "Borrowed money that isn't due for more than a year — like a long mortgage.",
  Liabilities:
    "Everything the company owes to others — loans, unpaid bills, and other promises to pay.",

  CommonStock:
    "The accounting value of shares that owners have put into the company.",
  RetainedEarnings:
    "Profits the company kept over time instead of paying out as dividends — savings from past good years.",
  Equity:
    "What's left for owners after subtracting everything owed from everything owned. The company's net worth.",
} as const;

export type FundamentalTipKey = keyof typeof FUNDAMENTAL_TIPS;

export function tipFor(key: string): string | undefined {
  return FUNDAMENTAL_TIPS[key as FundamentalTipKey];
}
