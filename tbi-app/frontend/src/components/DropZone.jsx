import { useState, useRef } from 'react';
import { useT } from '../i18n/LanguageContext.jsx';

const DropZone = ({ file, onChange }) => {
  const t = useT();
  const [drag, setDrag] = useState(false);
  const ref = useRef();

  const onDrop = (e) => {
    e.preventDefault();
    setDrag(false);
    const f = e.dataTransfer.files[0];
    if (f) onChange(f);
  };

  return (
    <div
      className={`dz${drag ? ' over' : ''}${file ? ' has' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={onDrop}
      onClick={() => ref.current.click()}
    >
      <input
        ref={ref}
        type="file"
        accept=".nii,.gz,.nii.gz"
        style={{ display: 'none' }}
        onChange={(e) => e.target.files[0] && onChange(e.target.files[0])}
      />
      {file ? (
        <>
          <div style={{ fontSize: 44, marginBottom: 8 }}>✅</div>
          <div style={{ fontWeight: 700, fontSize: 16 }}>{file.name}</div>
          <div style={{ fontSize: 13, color: 'var(--t3)', marginTop: 4 }}>
            {(file.size / 1024 / 1024).toFixed(1)} MB · {t('upload.dropChange')}
          </div>
        </>
      ) : (
        <>
          <div style={{ fontSize: 52, marginBottom: 12, opacity: 0.65 }}>🧠</div>
          <div style={{ fontWeight: 600, fontSize: 16, color: 'var(--text)' }}>
            {t('upload.dropPrompt')}
          </div>
          <div style={{ fontSize: 13, color: 'var(--t3)', marginTop: 6 }}>
            {t('upload.dropFormats')} <strong>.nii</strong> · <strong>.gz</strong> · {t('upload.dropClick')}
          </div>
        </>
      )}
    </div>
  );
};

export default DropZone;
