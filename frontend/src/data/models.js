// Strings (name, desc, tooltip, badge labels, step labels, metric labels) live
// in src/i18n/translations.js under keys derived from the IDs here. Stable IDs:
//   - model.id        → resolves models.{id}.name / .fullName / .desc / .tooltip
//   - model.badge     → resolves badge.{badge}
//   - model.metricLabel → resolves metrics.{metricLabel}
//   - step (string)   → resolves steps.{step}.name / .det
//   - metric tuple [key, value] → key resolves metrics.{key}; value is shown as-is
//
// Historical note: the first card was SPM12/DARTEL. We migrated to
// deepmriprep because SPM12 produced GM maps that were not reproducible
// between macOS (training) and Linux Docker (inference). deepmriprep is
// pure PyTorch → cross-platform OK.
//
// The Hybrid model (CNN + SVM) was discarded: the optimal fusion on
// validation gave w_CNN=1.00 — global volumetric features add no signal
// on top of deepmriprep maps. Documented as an experimental finding in
// the thesis.
export const MODELS = [
  {
    id: 'deepmriprep',
    metricLabel: 'aucRoc',
    metricVal: '80%',
    badge: 'classification',
    type: 'classification',
    steps: ['load', 'robex', 'dmpVbm', 'classify'],
    metrics: [
      ['aucRoc',      '79.7 %'],
      ['sensitivity', '55.8 %'],
      ['specificity', '88.4 %'],
      ['accuracy',    '72.1 %'],
    ],
  },
  {
    id: 'nnunet',
    metricLabel: 'dscMean',
    metricVal: '82.5%',
    badge: 'segmentation',
    type: 'segmentation',
    steps: ['load', 'robex', 'nnunetPre', 'nnunetInfer', 'nnunetPost'],
    metrics: [
      ['dscMean',     '82.5 %'],
      ['hausdorff95', '9.4 mm'],
      ['sensitivity', '90.5 %'],
      ['specificity', '78.9 %'],
    ],
    recommended: true,
  },
];
