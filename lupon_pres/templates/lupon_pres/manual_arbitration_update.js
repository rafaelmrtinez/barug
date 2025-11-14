// MANUAL UPDATE REQUIRED FOR LIVE FLOW
// The arbitration choice cannot be automatically added due to text matching issues
// 
// In the JavaScript FLOW_STEPS object, find the kp9_mediation step and update its choices array to:

choices: [
  { label: "Both attended → SETTLED", next: "kp16_mediation" },
  { label: "Both attended → NOT SETTLED → Constitute Pangkat", next: "kp10" },
  { label: "Both attended → NOT SETTLED → Agree to Arbitration", next: "kp14_arbitration_agree" },
  { label: "Respondent NO SHOW (counts as Hearing #1)", onClick: () => handleNoShow('RESPONDENT') },
  { label: "Complainant NO SHOW (counts as Hearing #1)", onClick: () => handleNoShow('COMPLAINANT') },
  { label: "Both NO SHOW (counts as Hearing #1)", onClick: () => handleNoShow('BOTH') }
]

// This adds the missing arbitration path when both parties attend PB mediation but it's not settled.