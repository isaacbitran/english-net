import type { Neuron } from "./types";

/* Deterministic fake probabilities for MOCK mode (no API key needed). Keyword heuristics, not a model. */

const ATTACK = /ignore (all |any |the )?(previous|prior|above)|system prompt|\bDAN\b|do anything now|pretend|jailbr|developer mode|no (rules|restrictions|filters)|unfiltered|override|disregard|prompt template|you are now|from now on/gi;

const RULES: Record<string, RegExp> = {
  override_instructions: /ignore|forget|override|disregard/i,
  reveal_system_prompt: /system prompt|prompt template|hidden instructions|reveal|print your/i,
  new_persona_no_rules: /no (rules|restrictions|filters|limits)|unrestricted|unfiltered/i,
  named_jailbreak: /\bDAN\b|do anything now|developer mode|jailbr/i,
  claims_authority: /i am (your|the) (developer|admin)|openai|system message|\[system\]/i,
  fictional_wrapper: /story|roleplay|pretend|hypothetical|imagine/i,
  two_responses: /two (answers|responses)|\[🔓|jailbroken/i,
  demands_no_refusal: /never refuse|don'?t refuse|no apolog/i,
  assistant_persona_defined: /you are now|from now on|act as|you will/i,
  immunity_claims: /free from|broken free|not bound/i,
  mentions_ai_rules: /rules|guidelines|policy|policies|filters/i,
  requests_confirmation_phrase: /confirm|say ["']?understood|reply with/i,
  mode_switch_command: /^\s*[/$[]/m,
  urgent_interrupt: /\b(stop|attention|new task)\b/i,
};

const BENIGN = /^(normal_question|benign_roleplay|structured_task_format|polite_simple_request|meta_about_prompting)$/;

function jitter(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return ((h >>> 0) % 1000) / 1000; // 0..1
}

export function mockAnswer(n: Neuron, state: Record<string, unknown>): number {
  if (n.layer === 2) {
    const f = Object.values((state.findings ?? {}) as Record<string, string>);
    const yes = f.filter((w) => w === "yes").length;
    return Math.min(0.95, 0.05 + (yes / Math.max(1, f.length)) * 0.9);
  }
  const text = String(state.text ?? "");
  const hits = (text.match(ATTACK) ?? []).length;
  const j = jitter(n.id + text) * 0.08;
  if (BENIGN.test(n.id)) return hits ? 0.06 + j : 0.82 + j;
  if (RULES[n.id]?.test(text)) return Math.min(0.97, 0.78 + 0.05 * hits + j);
  return Math.min(0.9, 0.03 + 0.12 * hits + j);
}
