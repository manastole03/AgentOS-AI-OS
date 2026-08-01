{{- define "healthos.name" -}}healthos{{- end }}
{{- define "healthos.fullname" -}}{{ .Release.Name }}{{- end }}
{{- define "healthos.labels" -}}
app.kubernetes.io/part-of: healthos
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}
