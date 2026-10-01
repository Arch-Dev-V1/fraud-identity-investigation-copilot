# Eval case set — please review

50 cases: **17 high**, **17 low**, **16 medium**

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
| 11 | Orlaith Fennimore | **high** | pass | 2016-11 (+27y) ⚠ | 1 | 73% | 0 | address · 508d · 12,43; device_id · 9d · 12 |
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
| 25 | Emeka Oduya | **medium** | pass | 2004-01 (+18y) | 0 | 25% | 0 | ip_address · 392d · 15,19,48 |
| 26 | Jarrell Okonjo-Pike | **high** | pass | 2017-02 (+29y) ⚠ | 1 | 76% | 0 | address · 303d · 27; device_id · 8d · 27,28,29; ip_address · 8d · 27,29 |
| 27 | Lissandra Beauchene | **high** | pass | 2017-06 (+26y) ⚠ | 1 | 72% | 0 | address · 303d · 26; device_id · 8d · 26,28; ip_address · 8d · 26 |
| 28 | Everard Nakashima | **high** | pass | 2016-12 (+30y) ⚠ | 1 | 77% | 0 | device_id · 8d · 26,27; ip_address · 3d · 29 |
| 29 | Shondra Villalpando | **high** | pass | 2017-09 (+24y) ⚠ | 1 | 74% | 0 | device_id · 260d · 26,50; ip_address · 7d · 26,28 |
| 30 | Caspian Motshwane | **high** | pass | 2017-04 (+27y) ⚠ | 1 | 79% | 0 | address · 5d · 31; email · 5d · 31 |
| 31 | Verity Oyelowo-Hart | **high** | pass | 2016-10 (+27y) ⚠ | 1 | 78% | 0 | address · 5d · 30; email · 5d · 30 |
| 32 | Thaddea Quillfeather | **high** | pass | 2018-08 (+34y) ⚠ | 1 | 73% | 0 | device_id · 282d · 46 |
| 33 | Brennus Adeyemi-Croft | **high** | pass | 2018-03 (+31y) ⚠ | 1 | 75% | 0 | none |
| 34 | Rosalind Featheringay | **low** | pass | 1969-08 (+18y) | 0 | 25% | 0 | none |
| 35 | Obadiah Winterbourne | **low** | pass | 2003-11 (+0y) | 0 | 23% | 0 | none |
| 36 | Anneliese Vartoogian | **low** | pass | 2014-07 (+18y) | 1 | 10% | 0 | none |
| 37 | Ezekiel Thanh-Nguyen | **low** | pass | 1999-03 (+19y) | 0 | 25% | 1 | phone · 531d · 44 |
| 38 | Marguerite Abaroa | **low** | pass | 2019-11 (+37y) ⚠ | 0 | 23% | 0 | none |
| 39 | Fitzgerald Amponsah | **low** | pass | 2018-05 (+41y) ⚠ | 0 | 25% | 0 | none |
| 40 | Delphine Castellanos | **low** | pass | 1987-06 (+18y) | 0 | 52% | 0 | none |
| 41 | Peregrine Oyedepo | **low** | pass | 2017-10 (+18y) | 0 | 23% | 0 | none |
| 42 | Ignacio Strathmore | **medium** | pass | 2003-02 (+9y) ⚠ | 0 | 25% | 0 | none |
| 43 | Clementine Byrd-Nakamura | **medium** | pass | 2004-01 (+19y) | 0 | 25% | 0 | address · 441d · 11 |
| 44 | Horatio Mbeki-Lund | **medium** | pass | 2019-09 (+36y) ⚠ | 1 | 20% | 0 | phone · 531d · 37 |
| 45 | Saoirse Deverell | **medium** | pass | 2019-04 (+29y) ⚠ | 0 | 25% | 1 | none |
| 46 | Lucian Oyarzabal | **medium** | pass | 1997-11 (+18y) | 0 | 25% | 0 | device_id · 282d · 32 |
| 47 | Perpetua Adewale-Finch | **medium** | pass | 2005-05 (+13y) ⚠ | 1 | 19% | 0 | none |
| 48 | Amaury Lindgren-Osei | **medium** | pass | 2006-03 (+19y) | 0 | 25% | 0 | ip_address · 346d · 25 |
| 49 | Rosamund Tchaikovsky | **medium** | pass | 2008-07 (+27y) ⚠ | 0 | 25% | 0 | none |
| 50 | Kwabena Ferreira-Shaw | **medium** | pass | 2014-02 (+19y) | 0 | 23% | 0 | device_id · 224d · 29 |

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
- **26 Jarrell Okonjo-Pike** → `high`  ·  _ring, anchor, synthesized_  
  Ring D anchor: header gap ~29y, AU boost, device+IP across 4 applicants in 8 days.
- **27 Lissandra Beauchene** → `high`  ·  _ring, synthesized_  
  Ring D: header gap ~26y, AU boost, device+IP+address with the ring.
- **28 Everard Nakashima** → `high`  ·  _ring, synthesized_  
  Ring D: header gap ~30y, AU boost, device+IP with the ring.
- **29 Shondra Villalpando** → `high`  ·  _ring, synthesized_  
  Ring D: header gap ~25y, AU boost, IP+device with the ring.
- **30 Caspian Motshwane** → `high`  ·  _ring, anchor, synthesized_  
  Ring E: header gap ~27y, AU boost, email+address across a pair in 5 days.
- **31 Verity Oyelowo-Hart** → `high`  ·  _ring, synthesized_  
  Ring E: header gap ~27y, AU boost, email+address across a pair in 5 days.
- **32 Thaddea Quillfeather** → `high`  ·  _lone-synthetic, synthesized_  
  Header gap ~34y, AU boost, stacking to near-full utilization; only link is a device shared over 282 days. No tight ring velocity.
- **33 Brennus Adeyemi-Croft** → `high`  ·  _lone-synthetic, synthesized_  
  Header gap ~31y, AU boost, rapid stacking, no links at all. The purest test of whether the agent can reach high on the trajectory alone.
- **34 Rosalind Featheringay** → `low`  ·  _legitimate, synthesized_  
  Header back to 1969, consistent. Organic file, nothing shared.
- **35 Obadiah Winterbourne** → `low`  ·  _legitimate, thin-file, synthesized_  
  Header from enumeration at birth, two small accounts, low utilization.
- **36 Anneliese Vartoogian** → `low`  ·  _legitimate, thin-file, synthesized_  
  Header first observed two months after a parent's AU line — the ordinary shape of a teenager's first record.
- **37 Ezekiel Thanh-Nguyen** → `low`  ·  _legitimate, synthesized_  
  Header back to 1999, consistent. Organic file with one cured 30-day late.
- **38 Marguerite Abaroa** → `low`  ·  _legitimate, adult-issuance, synthesized_  
  Header gap with an explicit benign cause recorded, no AU, no links.
- **39 Fitzgerald Amponsah** → `low`  ·  _legitimate, adult-issuance, synthesized_  
  Header gap with an explicit benign cause recorded, no AU, no links.
- **40 Delphine Castellanos** → `low`  ·  _legitimate, first-party-abuse, synthesized_  
  Third first-party case: header consistent back to 1987, recent stacking all current.
- **41 Peregrine Oyedepo** → `low`  ·  _legitimate, thin-file, synthesized_  
  Header consistent with the claimed DOB, small ordinary file, no links.
- **42 Ignacio Strathmore** → `medium`  ·  _ambiguous, short-gap, synthesized_  
  Nine-year gap — too short for a built identity, too long to wave away. No links.
- **43 Clementine Byrd-Nakamura** → `medium`  ·  _ambiguous, wide-span-link, synthesized_  
  Header consistent, but shares the Ring C address over 441 days. Same building is the innocent reading.
- **44 Horatio Mbeki-Lund** → `medium`  ·  _ambiguous, adult-issuance, synthesized_  
  Benign cause recorded, but an AU boost and a shared phone over 531 days pull back.
- **45 Saoirse Deverell** → `medium`  ·  _ambiguous, conflicting, synthesized_  
  Header gap with no benign cause, no links, but a delinquency that was then cured.
- **46 Lucian Oyarzabal** → `medium`  ·  _ambiguous, wide-span-link, synthesized_  
  Header consistent, ordinary file, but shares a device with applicant 32 over 282 days.
- **47 Perpetua Adewale-Finch** → `medium`  ·  _ambiguous, short-gap, synthesized_  
  Thirteen-year gap with no benign cause either way, plus an AU boost.
- **48 Amaury Lindgren-Osei** → `medium`  ·  _ambiguous, wide-span-link, synthesized_  
  Header consistent, but shares an IP with applicant 25 over 346 days — carrier NAT is the innocent reading.
- **49 Rosamund Tchaikovsky** → `medium`  ·  _ambiguous, conflicting, synthesized_  
  A 27-year gap, which alone looks severe, but the file since is ordinary and nothing links it anywhere. Tests whether the gap dominates on its own.
- **50 Kwabena Ferreira-Shaw** → `medium`  ·  _ambiguous, wide-span-link, synthesized_  
  Header consistent, thin file, shares a device with a Ring D member over 224 days.
