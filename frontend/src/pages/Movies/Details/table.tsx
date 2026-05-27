import React, { FunctionComponent, useMemo } from "react";
import { useNavigate } from "react-router";
import { Badge, Group, Text, TextProps } from "@mantine/core";
import { faEllipsis } from "@fortawesome/free-solid-svg-icons";
import { ColumnDef } from "@tanstack/react-table";
import { isString } from "lodash";
import { useMovieSubtitleModification } from "@/apis/hooks";
import { useShowOnlyDesired } from "@/apis/hooks/site";
import { Action } from "@/components";
import { HistoryIcon } from "@/components/bazarr";
import Language from "@/components/bazarr/Language";
import SubtitleToolsMenu from "@/components/SubtitleToolsMenu";
import SimpleTable from "@/components/tables/SimpleTable";
import { filterSubtitleBy, toPython } from "@/utilities";
import { useProfileItemsToLanguages } from "@/utilities/languages";

const missingText = "Missing Subtitles";

interface Props {
  movie: Item.Movie | null;
  disabled?: boolean;
  profile?: Language.Profile;
  history?: History.Movie[];
}

const ScoreBadge: React.FC<{ score?: string | number | null }> = ({
  score,
}) => {
  if (score === undefined || score === null || score === "") {
    return (
      <Text c="dimmed" size="xs">
        —
      </Text>
    );
  }
  const pct = typeof score === "string" ? parseFloat(score) : score;
  const color = pct >= 90 ? "green" : pct >= 70 ? "yellow" : "red";
  return (
    <Badge color={color} size="sm" variant="light">
      {typeof score === "number" ? `${score}%` : score}
    </Badge>
  );
};

function isSubtitleTrack(path: string | undefined | null) {
  return !isString(path) || path.length === 0;
}

function isSubtitleMissing(path: string | undefined | null) {
  return path === missingText;
}

function buildLanguageKey(sub: {
  code2: string;
  hi?: boolean;
  forced?: boolean;
}): string {
  let key = sub.code2;
  if (sub.hi) key += ":hi";
  if (sub.forced) key += ":forced";
  return key;
}

const Table: FunctionComponent<Props> = ({ movie, profile, history }) => {
  const onlyDesired = useShowOnlyDesired();

  const profileItems = useProfileItemsToLanguages(profile);

  const { download, remove } = useMovieSubtitleModification();

  // Available subtitles for translate-from source — include embedded tracks
  // (backend handles bitmap exclusion at extraction time)
  const availableSources = useMemo(
    () => movie?.subtitles ?? [],
    [movie?.subtitles],
  );

  const historyMap = useMemo(() => {
    const map = new Map<string, History.Movie>();
    history?.forEach((h) => {
      if (!h.subtitles_path) return;
      if ([1, 2, 3].includes(h.action)) {
        if (!map.has(h.subtitles_path)) map.set(h.subtitles_path, h);
      }
    });
    return map;
  }, [history]);

  const embeddedScoreMap = useMemo(() => {
    const map = new Map<string, History.Movie>();
    history?.forEach((h) => {
      if (h.action === 7 && h.language?.code2) {
        const key = buildLanguageKey(h.language);
        if (!map.has(key)) map.set(key, h);
      }
    });
    return map;
  }, [history]);

  const statusMap = useMemo(() => {
    const map = new Map<string, Set<number>>();
    history?.forEach((h) => {
      if (!h.subtitles_path) return;
      if ([5, 6].includes(h.action)) {
        if (!map.has(h.subtitles_path)) map.set(h.subtitles_path, new Set());
        map.get(h.subtitles_path)!.add(h.action);
      }
    });
    return map;
  }, [history]);

  const navigate = useNavigate();

  const CodeCell = React.memo(({ item }: { item: Subtitle }) => {
    const { code2, path, hi, forced } = item;

    const selections = useMemo(() => {
      const list: FormType.ModifySubtitle[] = [];

      if (!isSubtitleMissing(path) && movie !== null) {
        list.push({
          type: "movie",
          // Embedded track: path is null/empty — pass empty string so backend
          // treats it as an embedded extraction request (translate only).
          path: isSubtitleTrack(path) ? "" : path!,
          id: movie.radarrId,
          language: code2,
          forced: toPython(forced),
          hi: toPython(hi),
          // Carry the source language so backend can extract the right track
          from_language: isSubtitleTrack(path) ? code2 : undefined,
        });
      }

      return list;
    }, [code2, path, forced, hi]);

    if (movie === null) {
      return null;
    }

    const { radarrId } = movie;

    if (isSubtitleMissing(path)) {
      return (
        <SubtitleToolsMenu
          selections={[]}
          missingLanguage={item}
          translationSources={availableSources}
          mediaId={radarrId}
          mediaType="movie"
          onAction={async (action) => {
            if (action === "edit") {
              navigate(
                `/subtitles/edit/movie/${radarrId}/${encodeURIComponent(buildLanguageKey(item))}`,
              );
            } else if (action === "search") {
              await download.mutateAsync({
                radarrId,
                form: {
                  language: code2,
                  forced,
                  hi,
                },
              });
            }
          }}
        >
          <Action label="Subtitle Actions" icon={faEllipsis}></Action>
        </SubtitleToolsMenu>
      );
    }

    return (
      <SubtitleToolsMenu
        selections={selections}
        embeddedTrack={isSubtitleTrack(path)}
        onAction={async (action) => {
          if (action === "view") {
            navigate(
              `/subtitles/preview/movie/${radarrId}/${encodeURIComponent(buildLanguageKey(item))}`,
            );
          } else if (action === "edit") {
            navigate(
              `/subtitles/edit/movie/${radarrId}/${encodeURIComponent(buildLanguageKey(item))}`,
            );
          } else if (action === "delete" && path) {
            await remove.mutateAsync({
              radarrId,
              form: {
                language: code2,
                forced,
                hi,
                path,
              },
            });
          }
        }}
      >
        <Action
          label="Subtitle Actions"
          icon={faEllipsis}
        ></Action>
      </SubtitleToolsMenu>
    );
  });

  const columns = useMemo<ColumnDef<Subtitle>[]>(
    () => [
      {
        header: "Subtitle Path",
        accessorKey: "path",
        cell: ({
          row: {
            original: { path },
          },
        }) => {
          const props: TextProps = {
            className: "table-primary",
          };

          if (isSubtitleTrack(path)) {
            return (
              <Text className="table-primary">Video File Subtitle Track</Text>
            );
          } else if (isSubtitleMissing(path)) {
            return (
              <Text {...props} c="var(--bz-text-tertiary)">
                {path}
              </Text>
            );
          } else {
            return <Text {...props}>{path}</Text>;
          }
        },
      },
      {
        header: "Language",
        accessorKey: "name",
        cell: ({ row }) => {
          if (row.original.path === missingText) {
            return (
              <Badge variant="missing">
                <Language.Text value={row.original} long></Language.Text>
              </Badge>
            );
          } else {
            return (
              <Badge>
                <Language.Text value={row.original} long></Language.Text>
              </Badge>
            );
          }
        },
      },
      {
        id: "score",
        header: "Score",
        cell: ({ row: { original } }) => {
          const record = !isSubtitleTrack(original.path)
            ? historyMap.get(original.path!)
            : embeddedScoreMap.get(buildLanguageKey(original));
          return <ScoreBadge score={record?.score} />;
        },
      },
      {
        id: "provider",
        header: "Provider",
        cell: ({ row: { original } }) => {
          const record = !isSubtitleTrack(original.path)
            ? historyMap.get(original.path!)
            : embeddedScoreMap.get(buildLanguageKey(original));
          if (!record?.provider)
            return (
              <Text c="dimmed" size="xs">
                —
              </Text>
            );
          return <Text size="xs">{record.provider}</Text>;
        },
      },
      {
        id: "status",
        header: "Status",
        cell: ({ row: { original } }) => {
          const actions = !isSubtitleTrack(original.path)
            ? statusMap.get(original.path!)
            : undefined;
          if (!actions?.size)
            return (
              <Text c="dimmed" size="xs">
                —
              </Text>
            );
          return (
            <Group gap={4}>
              {Array.from(actions).map((action) => (
                <HistoryIcon key={action} action={action} />
              ))}
            </Group>
          );
        },
      },
      {
        id: "code2",
        cell: ({ row: { original } }) => {
          return <CodeCell item={original} />;
        },
      },
    ],
    [CodeCell, historyMap, embeddedScoreMap, statusMap],
  );

  const data: Subtitle[] = useMemo(() => {
    const missing =
      movie?.missing_subtitles.map((item) => ({
        ...item,
        path: missingText,
      })) ?? [];

    let subtitles = movie?.subtitles ?? [];
    if (onlyDesired) {
      subtitles = filterSubtitleBy(subtitles, profileItems);
    }

    return [...subtitles, ...missing];
  }, [movie, onlyDesired, profileItems]);

  return (
    <SimpleTable
      columns={columns}
      data={data}
      tableStyles={{ emptyText: "No subtitles found for this movie" }}
    ></SimpleTable>
  );
};

export default Table;
