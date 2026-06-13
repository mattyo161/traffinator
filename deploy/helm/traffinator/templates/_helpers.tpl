{{/* Base name */}}
{{- define "traffinator.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "traffinator.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "traffinator.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Component fullnames */}}
{{- define "traffinator.backend.fullname" -}}{{ printf "%s-backend" (include "traffinator.fullname" .) }}{{- end -}}
{{- define "traffinator.frontend.fullname" -}}{{ printf "%s-frontend" (include "traffinator.fullname" .) }}{{- end -}}
{{- define "traffinator.postgres.fullname" -}}{{ printf "%s-postgres" (include "traffinator.fullname" .) }}{{- end -}}

{{/* Name of the Secret holding credentials (existing or chart-managed) */}}
{{- define "traffinator.secretName" -}}
{{- if .Values.secrets.existingSecret -}}
{{- .Values.secrets.existingSecret -}}
{{- else -}}
{{- include "traffinator.fullname" . -}}
{{- end -}}
{{- end -}}

{{/* Common labels */}}
{{- define "traffinator.labels" -}}
helm.sh/chart: {{ include "traffinator.chart" . }}
app.kubernetes.io/name: {{ include "traffinator.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/* Selector labels for a component (pass dict "ctx" . "component" "backend") */}}
{{- define "traffinator.selectorLabels" -}}
app.kubernetes.io/name: {{ include "traffinator.name" .ctx }}
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}
