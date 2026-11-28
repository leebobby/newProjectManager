// 四组配置与表单共用；选项值只读取后端，不在前端维护另一份默认值。
export const licenseFields = [
  { key: 'model', config: 'customer_machine_models', label: '机台类型' },
  { key: 'throughput_package', config: 'license_throughput_packages', label: '产率包' },
  { key: 'algorithm', config: 'license_algorithms', label: '高阶算法特性' },
  { key: 'optional_features', config: 'license_optional_features', label: '可选特性', multiple: true },
]
export function licenseChoices(config, field, current) {
  const values = field.multiple ? (current || []) : (current ? [current] : [])
  return [...new Set([...(config[field.config] || []), ...values])]
}
