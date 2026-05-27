import { FunctionComponent, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { Badge, MantineColor } from "@mantine/core";
import { useEpisodeSubtitleModification } from "@/apis/hooks";
import Language from "@/components/bazarr/Language";
import SubtitleToolsMenu from "@/components/SubtitleToolsMenu";
import { toPython } from "@/utilities";

function buildLanguageKey(sub: Subtitle): string {
  let key = sub.code2;
  if (sub.hi) key += ":hi";
  if (sub.forced) key += ":forced";
  return key;
}

interface Props {
  seriesId: number;
  episodeId: number;
  missing?: boolean;
  subtitle: Subtitle;
  availableSubtitles?: Subtitle[];
}

export const Subtitle: FunctionComponent<Props> = ({
  seriesId,
  episodeId,
  missing = false,
  subtitle,
  availableSubtitles,
}) => {
  const navigate = useNavigate();
  const { remove, download } = useEpisodeSubtitleModification();

  const [opened, setOpen] = useState(false);

  // falsy path (null, undefined, "") means this is an embedded (in-container) subtitle track
  const isEmbedded = !subtitle.path;

  const variant: MantineColor | undefined = useMemo(() => {
    if (opened && (missing || !isEmbedded)) {
      return "highlight";
    } else if (missing) {
      return "missing";
    } else if (isEmbedded) {
      return "disabled";
    }
  }, [isEmbedded, missing, opened]);

  const selections = useMemo<FormType.ModifySubtitle[]>(() => {
    if (missing) return [];

    return [
      {
        id: episodeId,
        type: "episode",
        // Embedded track: empty path signals extraction on the backend
        path: subtitle.path ?? "",
        language: subtitle.code2,
        forced: toPython(subtitle.forced),
        hi: toPython(subtitle.hi),
        // Required by backend to identify which embedded track to extract
        from_language: isEmbedded ? subtitle.code2 : undefined,
      },
    ];
  }, [episodeId, subtitle.code2, subtitle.path, subtitle.forced, subtitle.hi, isEmbedded, missing]);

  // Translation sources: all available subtitles (embedded + external).
  // For missing subs the menu shows "Translate from X" items.
  // Backend handles bitmap codec exclusion at extraction time.
  const translationSources = useMemo(
    () => availableSubtitles ?? [],
    [availableSubtitles],
  );

  const badgeEl = (
    <Badge variant={variant}>
      <Language.Text value={subtitle} long={false}></Language.Text>
    </Badge>
  );

  // Interactive badges: no Tooltip wrapper around the menu target
  // (Tooltip.Floating breaks Menu.Target click handling)
  const ctx = badgeEl;

  return (
    <SubtitleToolsMenu
      menu={{
        trigger: "click",
        onOpen: () => setOpen(true),
        onClose: () => setOpen(false),
      }}
      selections={selections}
      embeddedTrack={isEmbedded}
      missingLanguage={missing ? subtitle : undefined}
      translationSources={missing ? translationSources : undefined}
      mediaId={episodeId}
      mediaType="episode"
      onAction={async (action) => {
        if (action === "view") {
          navigate(
            `/subtitles/preview/episode/${episodeId}/${encodeURIComponent(buildLanguageKey(subtitle))}`,
          );
        } else if (action === "edit") {
          navigate(
            `/subtitles/edit/episode/${episodeId}/${encodeURIComponent(buildLanguageKey(subtitle))}`,
          );
        } else if (action === "search") {
          await download.mutateAsync({
            seriesId,
            episodeId,
            form: {
              language: subtitle.code2,
              hi: subtitle.hi,
              forced: subtitle.forced,
            },
          });
        } else if (action === "delete" && subtitle.path) {
          await remove.mutateAsync({
            seriesId,
            episodeId,
            form: {
              language: subtitle.code2,
              hi: subtitle.hi,
              forced: subtitle.forced,
              path: subtitle.path,
            },
          });
        }
      }}
    >
      {ctx}
    </SubtitleToolsMenu>
  );
};
