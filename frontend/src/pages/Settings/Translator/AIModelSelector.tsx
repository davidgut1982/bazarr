import { FunctionComponent, useMemo } from "react";
import { useTranslatorModels } from "@/apis/hooks/translator";
import { SelectorOption } from "@/components";
import { Selector } from "@/pages/Settings/components";
import { aiTranslatorModelOptions } from "./options";

const AIModelSelector: FunctionComponent = () => {
  const { data: modelsResponse, isLoading } = useTranslatorModels();

  const modelOptions = useMemo((): SelectorOption<string>[] => {
    if (modelsResponse?.models && modelsResponse.models.length > 0) {
      return modelsResponse.models.map((model) => ({
        label: model.name + (model.is_default ? " (Recommended)" : ""),
        value: model.id,
      }));
    }
    return aiTranslatorModelOptions;
  }, [modelsResponse]);

  return (
    <Selector
      label="AI Model"
      options={modelOptions}
      settingKey="settings-translator-openrouter_model"
      placeholder={isLoading ? "Loading models..." : "Select a model..."}
      disabled={isLoading}
    />
  );
};

export default AIModelSelector;
