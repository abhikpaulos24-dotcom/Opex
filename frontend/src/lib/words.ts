// Plain-language glossary. Shown next to jargon (OEE, failure window...) and used in "Simple words" mode.

export const GLOSSARY: Record<string, { term: string; simple: string; explain: string }> = {
  oee: {
    term: "OEE",
    simple: "Overall efficiency",
    explain: "Overall Equipment Effectiveness: how much of the planned time made good parts at full speed. "
      + "It is availability × speed × quality. World class is 85%.",
  },
  p_fail: {
    term: "Chance of failure",
    simple: "Chance it breaks down",
    explain: "How likely the machine is to break down in the next 8 hours if nobody acts.",
  },
  window: {
    term: "Failure window",
    simple: "When it may break",
    explain: "The time range in which a breakdown is most likely (10% to 90% chance). Plan the repair before the start of it.",
  },
  confidence: {
    term: "Confidence",
    simple: "How sure we are",
    explain: "How sure OpEx is, based on how clear the sensor pattern is, past incidents, and how good the sensor data is.",
  },
  data_health: {
    term: "Data health",
    simple: "Sensor trust",
    explain: "Whether the sensors can be trusted: missing readings, noise, drift that other sensors don't confirm, calibration age.",
  },
  value_protected: {
    term: "Value protected",
    simple: "Money saved",
    explain: "Expected cost of doing nothing minus the expected cost of the recommended action.",
  },
};

export function label(key: keyof typeof GLOSSARY, simple: boolean): string {
  return simple ? GLOSSARY[key].simple : GLOSSARY[key].term;
}
