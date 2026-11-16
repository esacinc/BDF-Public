# agents/viz_slider.py
import os
import pydicom
import numpy as np
from pathlib import Path
import nibabel as nib
import plotly.graph_objects as go
from matplotlib import cm as mcm
import pandas as pd

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from log_helper.logger import get_logger
logger = get_logger()
from plotly.subplots import make_subplots

@dataclass
class Task:
    user_msg: str
    files: List[str] = field(default_factory=list)
    intent: Optional[str] = None
    kwargs: Dict[str, Any] = field(default_factory=dict)

@dataclass
class TaskResult:
    output: Any
    artifacts: Dict[str, Any] = field(default_factory=dict)
    next_tasks: List["Task"] = field(default_factory=list)
    debug: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ConversationState:
    memory: Dict[str, Any] = field(default_factory=dict)

class VizSliderAgent:
    """
    Slider-only visualization agent.

    Expected kwargs (all optional except image):
      - image_path: str (NIfTI path) OR image_array: np.ndarray (H,W,Z) or (H,W,Z,C)
      - mask_paths: list[str] OR mask_arrays: list[np.ndarray] (each mask H,W,Z or labelmap)
      - alpha: float in [0,1] (default 0.4)
      - cmaps: list[str] (matplotlib cmap names; optional, wraps if fewer than masks)
      - window_center: float (WL/WW windowing)
      - window_width: float
      - per_slice_minmax: bool (default True if no WL/WW provided)
      - interactive: bool (default True => slider; False => static mid slice)
      - max_dim: int (downsample longest side <= max_dim; default 512)

    It returns a Plotly Figure in TaskResult.output.
    """
    name  = "viz_slider"
    model = None  

    async def run(self, task: Task, state: ConversationState) -> TaskResult:
        logger.info("Start running VizSliderAgent.run()")
        try:
            kw = task.kwargs or {}
            image_path       = kw.get("image_path") or state.memory.get("image_path")
            image_array      = kw.get("image_array") or state.memory.get("image_array")
            mask_paths       = kw.get("mask_paths") or state.memory.get("mask_paths") \
                               or state.memory.get("segmentations") or []
            mask_arrays      = kw.get("mask_arrays") or state.memory.get("mask_arrays") or []
            alpha            = float(kw.get("alpha", 0.4))
            cmaps            = kw.get("cmaps")  # optional list[str]
            window_center    = kw.get("window_center", None)
            window_width     = kw.get("window_width", None)
            per_slice_minmax = bool(kw.get("per_slice_minmax", (window_center is None or window_width is None)))
            interactive      = bool(kw.get("interactive", True))
            max_dim          = int(kw.get("max_dim", 512))

            logger.info(f"[DEBUG] viz_slider {task.kwargs}")
            # Defaults if cmaps not provided
            DEFAULT_CMAPS = [
                "jet", "spring", "summer", "autumn", "winter",
                "cool", "hot", "viridis", "plasma", "magma", "cividis"
            ]
            if not cmaps:
                cmaps = DEFAULT_CMAPS
            
            # Load image volume 
            if image_array is not None:
                vol = self._ensure_3d(self._nan_clean(np.asarray(image_array)))
            elif image_path:
                if os.path.isdir(image_path):
                    # If it's a directory, use the DICOM loader
                    vol = self._load_dicom_directory(image_path)
                else:
                    # Otherwise, assume it's a single NIfTI file
                    vol = self._load_nifti(image_path)
            else:
                return TaskResult(output="VizSlider: Provide either 'image_path' or 'image_array'.")
            logger.info(f"[DEBUG] loaded image volume: {vol}")

            H, W, Z = vol.shape
            if Z < 1:
                return TaskResult(output=f"VizSlider: Volume has no slices (shape={vol.shape}).")

            # Prepare masks 
            mask_vols = self._prepare_masks(mask_paths, mask_arrays)  
            # Validate shape compatibility
            for mv in mask_vols:
                if mv.shape != vol.shape:
                    return TaskResult(
                        output=f"VizSlider: mask shape {mv.shape} != image shape {vol.shape}. "
                               "Resampling required."
                    )

            #  Map image to uint8 slices 
            if (window_center is not None) and (window_width is not None):
                base_slices = [
                    self._downsample2d(
                        self._window_to_uint8(vol[:, :, z], window_center, window_width), max_dim
                    )
                    for z in range(Z)
                ]
            else:
                base_slices = [
                    self._downsample2d(sl, max_dim)
                    for sl in self._per_slice_minmax_uint8(vol)
                ]

            # Downsample masks using the same stride approach
            if mask_vols:
                mask_slices_per_z = []
                for z in range(Z):
                    mslices = []
                    for mv in mask_vols:
                        sl = mv[:, :, z].astype(np.uint8)
                        sl = self._downsample2d(sl, max_dim)
                        mslices.append(sl)
                    mask_slices_per_z.append(mslices)
            else:
                mask_slices_per_z = [[] for _ in range(Z)]

            # Build either an interactive frame-based slider OR a static montage depending on requested layout
            nz = len(base_slices)
            mid = nz // 2

            requested_layout = kw.get("layout", None) or state.memory.get("layout", None)
            num_slices_req = kw.get("num_slices", None)

            # If user requested a montage layout, build subplots of selected slices
            if requested_layout and str(requested_layout).lower() == "montage":
                # Determine number of slices to include
                if num_slices_req is None:
                    k = min(5, nz)
                else:
                    k = min(int(num_slices_req), nz)

                # Select slice indices (random if asked for random sampling)
                import random as _rand
                try:
                    selected_idx = _rand.sample(range(nz), k)
                except Exception:
                    selected_idx = list(range(min(k, nz)))
                selected_idx.sort()

                # Create montage subplots (single row)
                fig = make_subplots(rows=1, cols=len(selected_idx), subplot_titles=[f"Slice {i}" for i in selected_idx])
                for col_i, z in enumerate(selected_idx, start=1):
                    rgba = self._rgba_stack_with_cmaps(base_slices[z], mask_slices_per_z[z], alpha, cmaps)
                    fig.add_trace(go.Image(z=rgba), row=1, col=col_i)
                    # hide axes ticks
                    fig.update_xaxes(showticklabels=False, row=1, col=col_i)
                    fig.update_yaxes(showticklabels=False, row=1, col=col_i)

                fig.update_layout(margin=dict(l=0, r=0, t=30, b=0))

            else:
                # Build RGBA frames for interactive slider
                frames = []
                for z in range(nz):
                    rgba = self._rgba_stack_with_cmaps(base_slices[z], mask_slices_per_z[z], alpha, cmaps)
                    frames.append(go.Frame(data=[go.Image(z=rgba)], name=str(z)))

                fig = go.Figure(
                    data=[go.Image(z=self._rgba_stack_with_cmaps(base_slices[mid], mask_slices_per_z[mid], alpha, cmaps))],
                    frames=frames,
                )

                if interactive and nz > 1:
                    fig.update_layout(
                        sliders=[{
                            "active": mid,
                            "currentvalue": {"prefix": "Slice "},
                            "steps": [
                                {"label": str(k), "method": "animate",
                                 "args": [[str(k)], {"mode": "immediate",
                                                      "frame": {"duration": 0, "redraw": True},
                                                      "transition": {"duration": 0}}]}
                                for k in range(nz)
                            ]
                        }],
                        margin=dict(l=0, r=0, t=0, b=0)
                    )
                else:
                    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))

            arts = {
                "image_path": str(image_path) if image_path else None,
                "mask_paths": [str(p) for p in (mask_paths or [])],
                "num_slices": Z
            }

            metadata_df = pd.DataFrame({
                "image_shape": [str(vol.shape)],
                "num_slices": [Z],
                "num_masks_applied": [len(mask_vols)],
                "window_center": [window_center],
                "window_width": [window_width],
                "downsample_dimension": [max_dim]
            })

            metadata_json = metadata_df.to_json(orient="records")

            logger.info(f"[DEBUG] viz_slider generated a figure with artifacts {arts}")

            # 4. Return the Plotly Figure object as the TaskResult.output so callers/tools
            # can choose to upload/serialize it (or fall back to the compact metadata).
            # Keep metadata in artifacts for lightweight inspection.
            arts["metadata_json"] = metadata_json
            return TaskResult(output=fig, artifacts=arts)

        except Exception as e:
            logger.debug(f"There was an exception in VisSlider: {e}")
            return TaskResult(output=f"VizSlider error: {e}")

    # Helpers
    def _ensure_3d(self, vol: np.ndarray) -> np.ndarray:
        """Accept (H,W,Z) or (H,W,Z,C) and return (H,W,Z)."""
        if vol.ndim == 4 and vol.shape[-1] > 1:
            return vol[..., 0]
        if vol.ndim == 4 and vol.shape[-1] == 1:
            return vol[..., 0]
        if vol.ndim != 3:
            raise ValueError(f"Expected 3D volume (H,W,Z); got {vol.shape}")
        return vol

    def _nan_clean(self, x: np.ndarray) -> np.ndarray:
        return np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)

    def _downsample2d(self, arr: np.ndarray, max_dim: int) -> np.ndarray:
        """Stride downsample to keep largest side <= max_dim."""
        h, w = arr.shape[:2]
        scale = max(h, w) / float(max_dim)
        if scale <= 1:
            return arr
        step = int(np.ceil(scale))
        return arr[::step, ::step] if arr.ndim == 2 else arr[::step, ::step, ...]

    def _window_to_uint8(self, arr: np.ndarray, center: float, width: float) -> np.ndarray:
        lo, hi = center - width/2.0, center + width/2.0
        arr = np.clip(arr, lo, hi)
        arr = (arr - lo) / (hi - lo + 1e-6)
        return (arr * 255).astype(np.uint8)

    def _per_slice_minmax_uint8(self, vol: np.ndarray):
        out = []
        for z in range(vol.shape[2]):
            sl = vol[:, :, z]
            mn, mx = np.nanmin(sl), np.nanmax(sl)
            if not np.isfinite([mn, mx]).all() or mx <= mn:
                out.append(np.zeros_like(sl, dtype=np.uint8))
            else:
                sl = (sl - mn) / (mx - mn + 1e-6)
                out.append((sl * 255).astype(np.uint8))
        return out

    def _load_nifti(self, path: str) -> np.ndarray:
        x = nib.load(str(Path(path))).get_fdata()
        logger.info(f"[DEBUG] _load_nifti function with path: {path} and loaded type: {type(x)}")
        return self._ensure_3d(self._nan_clean(x))

    def _to_mask_list(self, arr: np.ndarray):
        """
        Convert a 3D mask (binary or labelmap) to a list of binary masks.
        - If binary {0,1}, returns [mask].
        - If labelmap (ints), splits into one mask per label (excluding 0).
        """
        arr = np.asarray(arr)
        uniq = np.unique(arr[~np.isnan(arr)]) if np.isnan(arr).any() else np.unique(arr)
        if arr.dtype.kind in "iu":
            labels = [int(u) for u in uniq if u != 0]
            if len(labels) <= 1:
                return [(arr > 0).astype(np.uint8)]
            masks = []
            for lab in labels:
                masks.append((arr == lab).astype(np.uint8))
            return masks
        else:
            return [(arr > 0).astype(np.uint8)]

    def _prepare_masks(self, mask_paths, mask_arrays):
        """Load/normalize all masks into a list of binary mask volumes (H,W,Z)."""
        vols = []
        for p in (mask_paths or []):
            vols.append(self._load_nifti(p))
        for a in (mask_arrays or []):
            vols.append(self._ensure_3d(self._nan_clean(np.asarray(a))))
        out = []
        for v in vols:
            out.extend(self._to_mask_list(v))
        return out

    def _rgba_stack_with_cmaps(self, base_uint8: np.ndarray, mask_slices, alpha: float, cmap_names):
        """
        base_uint8: (H,W) uint8
        mask_slices: list of 2D binary masks aligned to base
        alpha: float 0..1
        cmap_names: list[str]
        Returns (H,W,4) uint8 RGBA composite
        """
        h, w = base_uint8.shape
        rgba = np.stack([base_uint8, base_uint8, base_uint8], axis=-1).astype(np.float32)

        if not mask_slices:
            a = np.full((h, w, 1), 255, dtype=np.uint8)
            return np.concatenate([rgba.astype(np.uint8), a], axis=-1)

        for i, m in enumerate(mask_slices):
            if m is None:
                continue
            sl = (m > 0).astype(np.uint8)
            if sl.max() == 0:
                continue
            cmap = mcm.get_cmap(cmap_names[i % len(cmap_names)])
            col = (np.array(cmap(1.0)) * 255).astype(np.uint8)  # solid RGBA color
            mask_idx = sl.astype(bool)
            rgba[mask_idx, 0] = (1 - alpha) * rgba[mask_idx, 0] + alpha * col[0]
            rgba[mask_idx, 1] = (1 - alpha) * rgba[mask_idx, 1] + alpha * col[1]
            rgba[mask_idx, 2] = (1 - alpha) * rgba[mask_idx, 2] + alpha * col[2]

        a = np.full((h, w, 1), 255, dtype=np.uint8)
        return np.concatenate([rgba.astype(np.uint8), a], axis=-1)

    def _load_dicom_directory(self, directory_path: str) -> np.ndarray:
        """Reads all .dcm files in a directory and stacks them into a 3D volume."""
        logger.info(f"Loading DICOM files from directory: {directory_path}")
        dicom_files = sorted(Path(directory_path).glob('*.dcm'))
        if not dicom_files:
            raise FileNotFoundError(f"No .dcm files found in {directory_path}")
        
        slices = [pydicom.dcmread(str(f)) for f in dicom_files]
    
        # Sort slices by instance number to ensure correct order
        slices.sort(key=lambda x: int(x.InstanceNumber))
    
        # Extract pixel arrays and stack them into a 3D numpy array
        image_arrays = [s.pixel_array for s in slices]
        image_volume = np.stack(image_arrays, axis=-1) # Stack along the Z-axis
    
        return image_volume
