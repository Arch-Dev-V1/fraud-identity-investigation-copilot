# Eval case set — please review

25 cases: **9 high**, **9 low**, **7 medium**

6 are the hand-built archetypes you've already seen; 19 are synthesized as
variations on them. Every applicant in this project is fabricated by design, so there
is no real traffic these could fail to represent — what they have to be is *fairly*
labelled, which is what the policy below is for.

## Labeling policy

```
a stated policy rather than per-case intuition, so a
disagreement is a disagreement about the policy and can be argued:

    high   — the credit-header gap is inconsistent with the claimed DOB with no
             benign cause recorded, AND either a ring link at tight velocity
             (one identifier across 3+ applicants inside ~30 days) or an
             authorized-user boost followed by rapid stacking to near-full
             utilization.
    medium — signals are present but each has a plausible innocent reading, or
             they conflict: a gap with a cured delinquency, a shared identifier
             over a span long enough to be a building or a carrier range.
    low    — the header is consistent with the claimed DOB, OR the gap has an
             explicit benign cause recorded, OR there are no links and both the
             trajectory and the payment history are ordinary.

    A recorded benign cause carries a case to `low` on its own, EXCEPT where it
    comes with both an authorized-user boost and a shared identifier — the two
    together are the maturation pattern, and that returns the case to `medium`.
    This clause is what separates 15 (benign cause, a wide IP link, no AU →
    low) from 21 (benign cause, a wide phone link, AU boost → medium). Without
    it those two labels look arbitrary.
```

`low` means low confidence the **identity is fabricated** — not that the application is
fine. Applicants 5 and 18 are real people running first-party abuse: correctly `low` on
synthetic identity, still a problem for the lender.

## The cases

| id | name | expected | eCBSV | header gap | AU | util | delinq | links (type · span · partners) |
|---|---|---|---|---|---|---|---|---|
| 1 | Marcus Delane Hoyt | **high** | pass | 2016-08 (+25y) ⚠ | 2 | 62% | 0 | address · 550d · 2,20; device_id · 11d · 2,3; ip_address · 11d · 2,3; phone · 204d · 3 |
| 2 | Tressa Lindqvist | **high** | pass | 2015-11 (+27y) ⚠ | 1 | 54% | 0 | address · 285d · 1; device_id · 11d · 1,3; email · 18d · 3; ip_address · 11d · 1,3 |
| 3 | Devon Aguayo-Pratt | **high** | pass | 2016-05 (+23y) ⚠ | 1 | 68% | 1 | device_id · 11d · 1,2; email · 18d · 2; ip_address · 11d · 1,2; phone · 204d · 1 |
| 4 | Priya Raghunathan | **low** | pass | 2019-09 (+16y) | 1 | 49% | 0 | none |
| 5 | Oscar Bellweather | **low** | pass | 1997-04 (+18y) | 0 | 57% | 0 | none |
| 6 | Nadia Osei-Kwame | **low** | pass | 2021-10 (+35y) ⚠ | 0 | 64% | 1 | none |
| 7 | Keshaun Vrabel | **high** | pass | 2017-03 (+27y) ⚠ | 1 | 78% | 0 | address · 265d · 8; email · 6d · 8,9; ip_address · 6d · 8,9 |
| 8 | Marlee Ostrowski | **high** | pass | 2016-09 (+29y) ⚠ | 1 | 73% | 0 | address · 265d · 7; device_id · 4d · 9; email · 6d · 7,9; ip_address · 6d · 7,9 |
| 9 | Donte Kirkbride | **high** | pass | 2017-07 (+25y) ⚠ | 1 | 78% | 0 | device_id · 4d · 8; email · 6d · 7,8; ip_address · 6d · 7,8 |
| 10 | Sylvan Brightmore | **high** | pass | 2019-02 (+34y) ⚠ | 1 | 75% | 0 | device_id · 266d · 23 |
| 11 | Orlaith Fennimore | **high** | pass | 2016-11 (+27y) ⚠ | 1 | 73% | 0 | address · 9d · 12; device_id · 9d · 12 |
| 12 | Rhett Calloway-Brees | **high** | pass | 2017-01 (+26y) ⚠ | 1 | 77% | 0 | address · 9d · 11; device_id · 9d · 11 |
| 13 | Imogen Hartsfield | **low** | pass | 2020-06 (+16y) | 1 | 10% | 0 | none |
| 14 | Alton Pemberton | **low** | pass | 1976-05 (+18y) | 0 | 25% | 1 | phone · 589d · 21 |
| 15 | Tendai Mushonga | **low** | pass | 2020-08 (+36y) ⚠ | 0 | 23% | 0 | ip_address · 388d · 25 |
| 16 | Bernadette Oyelaran | **low** | pass | 1998-02 (+19y) | 0 | 25% | 0 | none |
| 17 | Desmond Achterberg | **low** | pass | 2002-09 (+0y) | 0 | 23% | 0 | none |
| 18 | Corwin Stapleton | **low** | pass | 1993-08 (+19y) | 0 | 52% | 0 | none |
| 19 | Yusuf Benkiran | **medium** | pass | 2004-04 (+8y) ⚠ | 0 | 25% | 0 | ip_address · 291d · 25 |
| 20 | Marisol Trevejo | **medium** | pass | 2001-10 (+18y) | 0 | 25% | 0 | address · 448d · 1 |
| 21 | Ignatius Rowlandson | **medium** | pass | 2019-05 (+38y) ⚠ | 1 | 20% | 0 | phone · 589d · 14 |
| 22 | Arabella Nkemdirim | **medium** | pass | 2018-12 (+30y) ⚠ | 0 | 25% | 1 | none |
| 23 | Thaddeus Quintrell | **medium** | pass | 1995-07 (+18y) | 0 | 25% | 0 | device_id · 266d · 10 |
| 24 | Priyanka Vellaisamy | **medium** | pass | 2005-09 (+12y) ⚠ | 1 | 19% | 0 | none |
| 25 | Emeka Oduya | **medium** | pass | 2004-01 (+18y) | 0 | 25% | 0 | ip_address · 392d · 15,19 |

⚠ = header gap flagged as inconsistent with the claimed DOB.

## Why each label

- **1 Marcus Delane Hoyt** → `high`  ·  _ring, anchor, hand-built_  
  Ring A anchor: header gap ~25y, AU boost, device+IP across 3 applicants in 11 days.
- **2 Tressa Lindqvist** → `high`  ·  _ring, hand-built_  
  Ring A: header gap ~27y, AU boost, shares address/device/IP with the ring.
- **3 Devon Aguayo-Pratt** → `high`  ·  _ring, hand-built_  
  Ring A: header gap ~23y, AU boost, shares phone/device/IP; already past due.
- **4 Priya Raghunathan** → `low`  ·  _legitimate, thin-file, hand-built_  
  Real 22-year-old: header consistent, parent's AU line, low utilization, no links.
- **5 Oscar Bellweather** → `low`  ·  _legitimate, first-party-abuse, hand-built_  
  Real person, 20y clean history then a stacking spree. First-party abuse, not synthetic.
- **6 Nadia Osei-Kwame** → `low`  ·  _legitimate, adult-issuance, hand-built_  
  Header gap with an explicit benign cause recorded (adult arrival). No links.
- **7 Keshaun Vrabel** → `high`  ·  _ring, anchor, synthesized_  
  Ring B anchor: header gap ~27y, AU boost, email+IP across 3 applicants in 6 days.
- **8 Marlee Ostrowski** → `high`  ·  _ring, synthesized_  
  Ring B: header gap ~29y, AU boost, shares email/IP/address/device with the ring.
- **9 Donte Kirkbride** → `high`  ·  _ring, synthesized_  
  Ring B: header gap ~25y, AU boost, shares email/IP/device with the ring.
- **10 Sylvan Brightmore** → `high`  ·  _lone-synthetic, synthesized_  
  Hardest high: header gap ~34y, AU boost, stacking to 75% utilization, and its only link is a device shared over 266 days — no tight ring velocity at all. Tests whether the agent can reach high without a ring to point at.
- **11 Orlaith Fennimore** → `high`  ·  _ring, anchor, synthesized_  
  Ring C: header gap ~27y, AU boost, address+device across a pair in 9 days.
- **12 Rhett Calloway-Brees** → `high`  ·  _ring, synthesized_  
  Ring C: header gap ~26y, AU boost, address+device across a pair in 9 days.
- **13 Imogen Hartsfield** → `low`  ·  _legitimate, thin-file, synthesized_  
  Header first observed a month after the parent's AU line — what a 16-year-old's first record looks like. No links.
- **14 Alton Pemberton** → `low`  ·  _legitimate, synthesized_  
  Header back to 1976, consistent. Organic trajectory, one cured 30-day late.
- **15 Tendai Mushonga** → `low`  ·  _legitimate, adult-issuance, synthesized_  
  Header gap with an explicit benign cause recorded (adult arrival). No links.
- **16 Bernadette Oyelaran** → `low`  ·  _legitimate, synthesized_  
  Header consistent, organic trajectory, a joint line closed in 2023. No links.
- **17 Desmond Achterberg** → `low`  ·  _legitimate, thin-file, synthesized_  
  Header from enumeration at birth, two small accounts, low utilization. No links.
- **18 Corwin Stapleton** → `low`  ·  _legitimate, first-party-abuse, synthesized_  
  Second first-party case: header consistent back to 1993, recent stacking all current.
- **19 Yusuf Benkiran** → `medium`  ·  _ambiguous, short-gap, synthesized_  
  Eight-year gap — too short to be a built identity, too long to ignore. No links.
- **20 Marisol Trevejo** → `medium`  ·  _ambiguous, wide-span-link, synthesized_  
  Header consistent, but shares the Ring A mail-drop address over 448 days. Same building is the innocent reading.
- **21 Ignatius Rowlandson** → `medium`  ·  _ambiguous, adult-issuance, synthesized_  
  Benign cause recorded for the gap, but an AU boost and a shared phone over 589 days pull the other way.
- **22 Arabella Nkemdirim** → `medium`  ·  _ambiguous, conflicting, synthesized_  
  Header gap with no benign cause, no links, but a cured delinquency — manufactured files are managed, real people miss payments.
- **23 Thaddeus Quintrell** → `medium`  ·  _ambiguous, wide-span-link, synthesized_  
  Header consistent, ordinary trajectory, but shares a device with applicant 10 over 266 days.
- **24 Priyanka Vellaisamy** → `medium`  ·  _ambiguous, short-gap, synthesized_  
  Twelve-year gap with no benign cause either way, plus an AU boost. No links.
- **25 Emeka Oduya** → `medium`  ·  _ambiguous, wide-span-link, synthesized_  
  Header consistent, but shares an IP with two flagged applicants over wide spans — carrier NAT is the innocent reading.
