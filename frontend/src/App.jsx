import { useState, useEffect } from 'react';
import Brain from './components/Brain.jsx';
import Footer from './components/Footer.jsx';
import LanguageToggle from './components/LanguageToggle.jsx';
import HomeScreen from './screens/HomeScreen.jsx';
import UploadScreen from './screens/UploadScreen.jsx';
import ProcessingScreen from './screens/ProcessingScreen.jsx';
import ResultsScreen from './screens/ResultsScreen.jsx';
import AboutScreen from './screens/AboutScreen.jsx';
import { useT } from './i18n/LanguageContext.jsx';
import { getAssetsStatus } from './api/client.js';

const App = () => {
  const t = useT();
  const [screen, setScreen] = useState('home');
  const [prevScreen, setPrevScreen] = useState('home');
  const [model, setModel] = useState(null);
  const [info, setInfo] = useState({});
  const [file, setFile] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [result, setResult] = useState(null);
  // Asset availability — fetched once at mount, used to disable cards/toggles
  // when the trained models or ROBEX binary are missing on the host volume.
  const [assets, setAssets] = useState(null);

  useEffect(() => {
    getAssetsStatus()
      .then(setAssets)
      .catch((e) => console.warn('[assets] could not fetch status:', e));
  }, []);

  const reset = () => {
    setModel(null);
    setInfo({});
    setFile(null);
    setJobId(null);
    setResult(null);
    setScreen('home');
  };

  const goAbout = () => {
    // Only remember the previous screen if we're not already on About —
    // otherwise re-clicking the "Acerca de" nav link while on About would
    // overwrite prevScreen with 'about' itself and the back button would
    // become a no-op.
    if (screen !== 'about') setPrevScreen(screen);
    setScreen('about');
  };

  const backFromAbout = () => setScreen(prevScreen);

  return (
    <div className="app">
      <nav className="nav">
        <div
          className="nav-left"
          style={{ cursor: screen !== 'processing' ? 'pointer' : 'default' }}
          onClick={screen !== 'processing' ? reset : undefined}
        >
          <Brain size={32} color="var(--primary)" />
          <span className="nav-title">
            VBM <em>App</em>
          </span>
          <span className="nav-version">{t('nav.versionBadge')}</span>
        </div>

        {/* Center: badge + name of the chosen model.
            Shown only while the user is actively inside a model flow
            (upload / processing / results) — hidden on home and about. */}
        <div className="nav-center">
          {model && ['upload', 'processing', 'results'].includes(screen) && (
            <div className="nav-model">
              <span className={`badge ${model.badge === 'segmentation' ? 'b-am' : 'b-bl'}`}>
                {t(`badge.${model.badge}`)}
              </span>
              <span className="nav-model-name">{t(`models.${model.id}.name`)}</span>
            </div>
          )}
        </div>

        <div className="nav-right">
          <button type="button" className="nav-about" onClick={goAbout}>
            {t('nav.about')}
          </button>
          <LanguageToggle />
        </div>
      </nav>

      <main className="main">
        {screen === 'home' && (
          <HomeScreen
            assets={assets}
            onSelect={(m) => {
              setModel(m);
              setScreen('upload');
            }}
          />
        )}
        {screen === 'upload' && (
          <UploadScreen
            model={model}
            assets={assets}
            onStart={(i, f, newJobId) => {
              setInfo(i);
              setFile(f);
              setJobId(newJobId);
              setResult(null);
              setScreen('processing');
            }}
            onBack={() => setScreen('home')}
          />
        )}
        {screen === 'processing' && (
          <ProcessingScreen
            model={model}
            info={info}
            jobId={jobId}
            onCancel={reset}
            onDone={(r) => {
              setResult(r);
              setScreen('results');
            }}
          />
        )}
        {screen === 'results' && (
          <ResultsScreen model={model} info={info} file={file} jobId={jobId} result={result} onReset={reset} />
        )}
        {screen === 'about' && <AboutScreen onBack={backFromAbout} />}
      </main>

      <Footer onAbout={goAbout} />
    </div>
  );
};

export default App;
