// Add arbitration choice to PB mediation "Both attended NOT SETTLED" outcome
// Update kp9_mediation choices to include:

choices: [
  { label: "Both attended → SETTLED", next: "kp16_mediation" },
  { label: "Both attended → NOT SETTLED → Proceed to Pangkat", next: "kp10" },
  { label: "Both attended → NOT SETTLED → Agree to Arbitration", next: "kp14_arbitration_agree" },
  { label: "Respondent NO SHOW (counts as Hearing #1)", onClick: () => handleNoShow('RESPONDENT') },
  { label: "Complainant NO SHOW (counts as Hearing #1)", onClick: () => handleNoShow('COMPLAINANT') },
  { label: "Both NO SHOW (counts as Hearing #1)", onClick: () => handleNoShow('BOTH') }
]