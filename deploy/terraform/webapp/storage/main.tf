##################################
# Media Bucket
#
# S3 bucket que permite a la aplicación
# leer y escribir libremente en tiempo de
# ejecución.
##################################
locals {
  bucket_name = "media.${var.domain_name}"
}

resource "aws_s3_bucket" "media" {
  bucket = local.bucket_name
}

resource "aws_iam_policy" "media" {
  name = "${local.bucket_name}-allow"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "s3:PutObject",
          "s3:GetObject"
        ],
        Resource = [
          "${aws_s3_bucket.media.arn}/*"
        ]
      },
      {
        Effect = "Allow",
        Action = [
          "s3:ListBucket"
        ],
        Resource = [
          aws_s3_bucket.media.arn
        ]
      }
    ]
  })
}
