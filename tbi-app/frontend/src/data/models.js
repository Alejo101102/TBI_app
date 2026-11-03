// Strings (name, desc, tooltip, badge labels, step labels, metric labels) live
// in src/i18n/translations.js under keys derived from the IDs here. Stable IDs:
//   - model.id        → resolves models.{id}.name / .fullName / .desc / .tooltip
//   - model.badge     → resolves badge.{badge}
//   - model.metricLabel → resolves metrics.{metricLabel}
//   - step (string)   → resolves steps.{step}.name / .det
//   - metric tuple [key, value] → key resolves metrics.{key}; value is shown as-is
export const MODELS = [
  {
    id: 'nnunet',
    metricLabel: 'dscMean',
    metricVal: '61.6%',
    badge: 'segmentation',
    type: 'segmentation',
    steps: ['load', 'robex', 'nnunetPre', 'nnunetInfer', 'nnunetPost'],
    metrics: [
      ['dscMean',      '61.6 %'],
      ['iou',          '55.4 %'],
      ['detSmall',     '11.8 %'],
      ['fpProportion', '67.7 %'],
    ],
  },
];
