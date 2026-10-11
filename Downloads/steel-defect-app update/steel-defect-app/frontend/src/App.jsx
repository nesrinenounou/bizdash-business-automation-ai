import { useState } from "react";

const API = "http://127.0.0.1:8000";

export default function App() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const pick = (f) => {
    if (!f) return;
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setResult(null);
    setError("");
  };

  const analyze = async () => {
    setLoading(true);
    setError("");
    try {
      const body = new FormData();
      body.append("file", file);
      const res = await fetch(`${API}/predict`, { method: "POST", body });
      if (!res.ok) throw new Error((await res.json()).detail || "Request failed");
      setResult(await res.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const sorted = result
    ? Object.entries(result.probabilities).sort((a, b) => b[1] - a[1])
    : [];

  return (
    <main>
      <h1>Steel Surface Defect Detection</h1>
      <p className="sub">EfficientNet-B0 features → XGBoost classifier</p>

      <label className="drop">
        {preview ? <img src={preview} alt="preview" /> : <span>Click to upload a steel surface image</span>}
        <input type="file" accept="image/*" hidden onChange={(e) => pick(e.target.files[0])} />
      </label>

      <button disabled={!file || loading} onClick={analyze}>
        {loading ? "Analyzing…" : "Analyze"}
      </button>
      {error && <p className="error">{error}</p>}

      {result && (
        <section>
          <h2>
            {result.prediction}
            <span> {(result.confidence * 100).toFixed(1)}%</span>
          </h2>
          {sorted.map(([name, p]) => (
            <div className="row" key={name}>
              <em>{name}</em>
              <div className="bar"><i style={{ width: `${p * 100}%` }} /></div>
              <b>{(p * 100).toFixed(1)}%</b>
            </div>
          ))}

          <h3>Why this result?</h3>
          <ul>{result.explanation.map((t, i) => <li key={i}>{t}</li>)}</ul>

          <div className="pair">
            <figure>
              <img src={`data:image/png;base64,${result.gradcam_png}`} alt="Grad-CAM" />
              <figcaption>Grad-CAM: where the CNN looked</figcaption>
            </figure>
            {result.segmentation_png && (
              <figure>
                <img src={`data:image/png;base64,${result.segmentation_png}`} alt="SAM2" />
                <figcaption>YOLO boxes + SAM2 masks</figcaption>
              </figure>
            )}
          </div>
          {result.detections?.map((d, i) => (
            <p className="det" key={i}>
              {d.label} {(d.confidence * 100).toFixed(1)}% · mask covers {d.mask_area_pct}% of the image
            </p>
          ))}
        </section>
      )}
    </main>
  );
}
