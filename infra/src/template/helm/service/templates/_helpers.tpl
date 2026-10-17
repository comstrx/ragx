{{- define "service.name" -}}
{{- .Values.name | default .Release.Name -}}
{{- end -}}

{{- define "service.labels" -}}
app.kubernetes.io/name: {{ include "service.name" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "service.selector" -}}
app.kubernetes.io/name: {{ include "service.name" . }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "service.secretRef" -}}
{{- .Values.secretRef | default (printf "%s-secrets" (include "service.name" .)) -}}
{{- end -}}

{{- define "service.ownerSecretRef" -}}
{{- .Values.ownerSecretRef | default (printf "%s-owner-secrets" (include "service.name" .)) -}}
{{- end -}}

{{- define "service.image" -}}
{{- printf "%s:%s" .Values.image.repository (.Values.image.tag | toString) -}}
{{- end -}}

{{- define "service.backupImage" -}}
{{- printf "%s:backup-%s" .Values.image.repository (.Values.image.tag | toString) -}}
{{- end -}}

{{- define "service.responseHeaders" -}}
{{- if or .set .remove -}}
filters:
  - type: ResponseHeaderModifier
    responseHeaderModifier:
    {{- with .set }}
      set:
      {{- range $name, $value := . }}
        - name: {{ $name }}
          value: {{ $value | quote }}
      {{- end }}
    {{- end }}
    {{- with .remove }}
      remove:
      {{- range . }}
        - {{ . }}
      {{- end }}
    {{- end }}
{{- end -}}
{{- end -}}

{{- define "service.pullSecrets" -}}
{{- with .Values.imagePullSecrets -}}
imagePullSecrets:
{{- range . }}
  - name: {{ . }}
{{- end }}
{{- end -}}
{{- end -}}
