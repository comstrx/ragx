data "aws_iam_policy_document" "app" {
  statement {
    sid       = "Storage"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
    resources = [var.storage_bucket_arn, "${var.storage_bucket_arn}/*"]
  }
}

data "aws_iam_policy_document" "backup" {
  statement {
    sid       = "Backups"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
    resources = [var.backup_bucket_arn, "${var.backup_bucket_arn}/*"]
  }
}

resource "aws_iam_group" "app" {
  name = "${var.name}-app"
}

resource "aws_iam_group_policy" "app" {
  name   = "${var.name}-app"
  group  = aws_iam_group.app.name
  policy = data.aws_iam_policy_document.app.json
}

resource "aws_iam_user" "app" {
  name = "${var.name}-app"
}

resource "aws_iam_user_group_membership" "app" {
  user   = aws_iam_user.app.name
  groups = [aws_iam_group.app.name]
}

resource "aws_iam_access_key" "app" {
  user = aws_iam_user.app.name
}

resource "aws_iam_group" "backup" {
  name = "${var.name}-backup"
}

resource "aws_iam_group_policy" "backup" {
  name   = "${var.name}-backup"
  group  = aws_iam_group.backup.name
  policy = data.aws_iam_policy_document.backup.json
}

resource "aws_iam_user" "backup" {
  name = "${var.name}-backup"
}

resource "aws_iam_user_group_membership" "backup" {
  user   = aws_iam_user.backup.name
  groups = [aws_iam_group.backup.name]
}

resource "aws_iam_access_key" "backup" {
  user = aws_iam_user.backup.name
}
