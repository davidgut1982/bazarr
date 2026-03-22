import { SelectorOption } from "@/components";

export const translatorOption: SelectorOption<string>[] = [
  { label: "Google Translate", value: "google_translate" },
  { label: "Gemini", value: "gemini" },
  { label: "Lingarr", value: "lingarr" },
  { label: "AI Subtitle Translator", value: "openrouter" },
];

export const aiTranslatorModelOptions: SelectorOption<string>[] = [
  { label: "Gemini 2.5 Flash (Recommended)", value: "google/gemini-2.5-flash-preview-05-20" },
  { label: "Gemini 2.5 Flash Lite (Fast & Cheap)", value: "google/gemini-2.5-flash-lite-preview-06-17" },
  { label: "GPT-4o Mini", value: "openai/gpt-4o-mini" },
  { label: "Claude 3 Haiku", value: "anthropic/claude-3-haiku" },
  { label: "Claude Haiku 4.5 (Extended Thinking)", value: "anthropic/claude-haiku-4.5" },
  { label: "LLaMA 4 Maverick", value: "meta-llama/llama-4-maverick" },
  { label: "Grok 4.1 Fast", value: "x-ai/grok-4.1-fast" },
  { label: "Kimi K2", value: "moonshotai/kimi-k2-0905" },
];

export const aiTranslatorReasoningOptions: SelectorOption<string>[] = [
  { label: "Disabled", value: "disabled" },
  { label: "Low (Minimal thinking)", value: "low" },
  { label: "Medium (Default)", value: "medium" },
  { label: "High (Extended thinking)", value: "high" },
];

export const aiTranslatorConcurrentOptions: SelectorOption<number>[] = [
  { label: "1 (Low)", value: 1 },
  { label: "2 (Default)", value: 2 },
  { label: "3", value: 3 },
  { label: "4", value: 4 },
  { label: "5 (High)", value: 5 },
];
