export function getRetryableUploads(selectedFiles) {
  return selectedFiles.filter((selected) => !['success', 'duplicate'].includes(selected.status))
}
