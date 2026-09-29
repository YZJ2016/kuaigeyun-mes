import { Human, type FaceResult } from '@vladmandic/human';

/** HSE FaceRes 输出维，见安装包 models/faceres.json 的 global_pooling/Mean。 */
export const FACERES_DESCRIPTOR_LENGTH = 1024;

/**
 * 模型在浏览器里按需下载，不打进 Electron。
 * 与已安装的 @vladmandic/human@3.3.6 自带 models 目录一致，宿主是该库 wasm 已使用的 jsDelivr。
 */
const MODEL_BASE_PATH = 'https://cdn.jsdelivr.net/npm/@vladmandic/human@3.3.6/models/';

let human: Human | null = null;

function getHuman(): Human {
  if (!human) {
    human = new Human({
      backend: 'webgl',
      modelBasePath: MODEL_BASE_PATH,
      debug: false,
      async: false,
      face: {
        enabled: true,
        detector: { enabled: true, rotation: false, maxDetected: 1, skipFrames: 0, skipTime: 0 },
        mesh: { enabled: true },
        iris: { enabled: false },
        emotion: { enabled: false },
        description: { enabled: true, skipFrames: 0, skipTime: 0 },
        antispoof: { enabled: false },
        liveness: { enabled: false },
      },
      body: { enabled: false },
      hand: { enabled: false },
      object: { enabled: false },
      gesture: { enabled: false },
    });
  }
  return human;
}

function faceResDescriptor(face: FaceResult): number[] | null {
  const embedding = face.embedding;
  if (!embedding || embedding.length !== FACERES_DESCRIPTOR_LENGTH) return null;
  return Array.from(embedding);
}

/** 从视频当前帧取 FaceRes 描述子。长度不是 1024 时抛错，调用方不得提交接口。 */
export async function captureFaceResDescriptor(video: HTMLVideoElement): Promise<number[]> {
  const result = await getHuman().detect(video);
  if (result.error) {
    throw new Error(String(result.error));
  }
  for (const face of result.face ?? []) {
    const descriptor = faceResDescriptor(face);
    if (descriptor) return descriptor;
  }
  const length = result.face?.[0]?.embedding?.length ?? 0;
  if (length > 0) {
    throw new Error(`人脸描述子长度为 ${length}，需要 ${FACERES_DESCRIPTOR_LENGTH}，未提交`);
  }
  throw new Error('未检测到人脸');
}
