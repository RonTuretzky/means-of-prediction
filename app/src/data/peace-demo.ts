// Public-safe historical replay index. No mail, mailbox identifiers or credentials.
// Scores describe the recorded integer judge run, not trading probabilities.
export const PEACE_DEMO = {
  id: "peace-2026",
  marketId: "5371292",
  question: "Nobel Peace Prize 2026 awarded to an individual?",
  result: "YES",
  replayedAt: "2026-10-21T01:35:44Z",
  chainId: 31337,
  localTransaction: "0x8b06085c0227a9fe9b17f3ae54f7f21fee2d2df1def4318d60566cbbc3a1a0ae",
  block: 130,
  gasUsed: 124075906,
  ruleHash: "0xf1ba951f9767de4eae4f2562b22bc4ad43db741fe3d30cecc5112a93eafece6d",
  rulesUrl: "https://polymarket.com/event/nobel-peace-prize-2026-awarded-to-an-individual",
  model: "alert-student-base-final-support-v1",
  reportedLaureate: "Navi Pillay",
  sources: [
    {
      id: "bbc", name: "BBC", domain: "bbc.com", mark: "BBC",
      url: "https://www.bbc.com/audio/play/m00331hm",
      excerpt: "Navanetham 'Navi' Pillay has been awarded the Nobel Peace Prize for 2026.",
      signedAt: "2026-10-18T02:58:28Z", expiresAt: "2026-10-25T02:58:28Z",
      support: 89.32, counter: 5.29,
    },
    {
      id: "cnn", name: "CNN", domain: "cnn.com", mark: "CNN",
      url: "https://www.cnn.com/world/video/nobel-prize-pillay-intv",
      excerpt: "2026 Nobel Peace Prize laureate Navi Pillay speaks to CNN.",
      signedAt: "2026-10-14T16:14:49Z", expiresAt: "2026-10-21T16:14:49Z",
      support: 85.39, counter: 6.38,
    },
    {
      id: "abc", name: "ABC", domain: "abc.net.au", mark: "ABC",
      url: "https://www.abc.net.au/news/2026-10-15/nobel-peace-prize-winner-navi-pillay-interview/107255774",
      excerpt: 'In her first Australian interview since winning the 2026 Nobel Peace Prize, Navanethem "Navi" Pillay',
      signedAt: "2026-10-15T02:56:44Z", expiresAt: "2026-10-22T02:56:44Z",
      support: 86.54, counter: 4.97,
    },
    {
      id: "rfi", name: "RFI", domain: "rfi.fr", mark: "RFI",
      url: "https://www.rfi.fr/en/international/20261014-nobel-prize-winner-navi-pillay-you-don-t-wait-for-a-million-people-to-be-killed",
      excerpt: 'The winner of the 2026 Nobel Peace Prize, South African judge Navanethem "Navi" Pillay, tells RFI',
      signedAt: "2026-10-14T18:09:03Z", expiresAt: "2026-10-21T18:09:03Z",
      support: 80.93, counter: 5.51,
    },
  ],
  predicates: [
    { title: "A named individual", detail: "The recorded reports identify Navi Pillay as a person." },
    { title: "Awarded, not merely nominated", detail: "The excerpts describe a winner or laureate." },
    { title: "The right award and year", detail: "All four excerpts name the 2026 Nobel Peace Prize." },
    { title: "Credible-reporting fallback", detail: "The replay evaluated agreement across BBC, CNN, ABC and RFI." },
  ],
} as const;
