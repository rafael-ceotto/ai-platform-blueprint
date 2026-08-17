{{/*
Chart name.
*/}}
{{- define "konsole-ai.name" -}}
{{- .Chart.Name -}}
{{- end -}}

{{/*
Fully qualified app name.
*/}}
{{- define "konsole-ai.fullname" -}}
{{- .Release.Name -}}
{{- end -}}

{{/*
Common labels.
*/}}
{{- define "konsole-ai.labels" -}}
helm.sh/chart: {{ printf "%s-%s" (include "konsole-ai.name" .) .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Selector labels for a given component (api / ollama / ui). Call as:
  include "konsole-ai.selectorLabels" (dict "root" $ "component" "api")
*/}}
{{- define "konsole-ai.selectorLabels" -}}
app.kubernetes.io/name: {{ include "konsole-ai.name" .root }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}
