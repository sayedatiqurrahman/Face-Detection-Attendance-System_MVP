"""
Face Engine — InsightFace wrapper for face detection and embedding extraction.

Uses buffalo_l model (lightweight, good for CPU).
Provides:
  - get_embedding(img)       : embedding of the first detected face
  - get_all_embeddings(img)  : list of {embedding, bbox} for all faces
"""

from insightface.app import FaceAnalysis
import numpy as np


# Initialise InsightFace with the buffalo_l model
# ctx_id = 0  → first GPU (use -1 for CPU only)
app = FaceAnalysis(name='buffalo_l')
app.prepare(ctx_id=0, det_size=(640, 640))


def get_embedding(img):
    """Return the 512-d embedding of the first detected face, or None if no face."""
    faces = app.get(img)
    if len(faces) == 0:
        return None
    return faces[0].embedding


def get_all_embeddings(img):
    """
    Return a list of dicts for every face detected in the image.
    Each dict: { 'embedding': np.ndarray (512,), 'bbox': [x1,y1,x2,y2] }
    Returns an empty list when no faces are found.
    """
    faces = app.get(img)
    results = []
    for face in faces:
        results.append({
            'embedding': face.embedding,
            'bbox': face.bbox.astype(int).tolist()
        })
    return results