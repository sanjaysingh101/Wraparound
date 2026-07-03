declare module "@mkkellogg/gaussian-splats-3d" {
  import type * as THREE from "three";

  export interface ViewerOptions {
    rootElement?: HTMLElement;
    selfDrivenMode?: boolean;
    useBuiltInControls?: boolean;
    sharedMemoryForWorkers?: boolean;
    dynamicScene?: boolean;
    cameraUp?: number[];
    initialCameraPosition?: number[];
    initialCameraLookAt?: number[];
  }

  export interface AddSplatSceneOptions {
    showLoadingUI?: boolean;
    progressiveLoad?: boolean;
    splatAlphaRemovalThreshold?: number;
    scale?: number[];
    rotation?: number[];
    position?: number[];
  }

  export class SplatMesh extends THREE.Object3D {
    getSplatCount(): number;
    setSplatScale?(scale: number): void;
    getSplatScale?(): number;
    setPointCloudModeEnabled?(enabled: boolean): void;
    material?: THREE.Material;
  }

  export class Viewer {
    constructor(options?: ViewerOptions);
    renderer: THREE.WebGLRenderer;
    threeScene: THREE.Scene;
    camera: THREE.PerspectiveCamera;
    controls?: { target: THREE.Vector3; update(): void };
    addSplatScene(path: string, options?: AddSplatSceneOptions): Promise<void>;
    start(): void;
    stop(): void;
    dispose(): Promise<void>;
    getSplatMesh(): SplatMesh | null;
    setRenderMode?(mode: number): void;
  }

  export const PlyLoader: {
    loadFromFileData(
      data: ArrayBuffer,
      minimumAlpha: number,
      compressionLevel: number,
      optimizeSplatData: boolean,
      sphericalHarmonicsDegree: number,
    ): Promise<{ bufferData: ArrayBuffer }>;
  };
}
