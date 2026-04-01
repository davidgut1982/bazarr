import type { ParseResult, SubtitleFormat } from "@/pages/SubtitleEditor/types";
import { srtSerializer } from "./srt";
import { assSerializer } from "./ass";
import { vttSerializer } from "./vtt";
import { subSerializer } from "./sub";
import { smiSerializer } from "./smi";
import { txtSerializer } from "./txt";
import { mplSerializer } from "./mpl";

export interface SubtitleSerializer {
  serialize(result: ParseResult): string;
}

const serializers: Record<SubtitleFormat, SubtitleSerializer> = {
  srt: srtSerializer,
  ass: assSerializer,
  ssa: assSerializer,
  vtt: vttSerializer,
  sub: subSerializer,
  smi: smiSerializer,
  txt: txtSerializer,
  mpl: mplSerializer,
};

export function getSerializer(format: SubtitleFormat): SubtitleSerializer {
  return serializers[format];
}
