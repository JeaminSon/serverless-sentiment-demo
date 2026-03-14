terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  backend "s3" {
      bucket = "sentiment-demo-jambread-2026"
      key = "terraform/state.tfstate"
      region = "ap-northeast-2"
  }
}

provider "aws" {
  region = "ap-northeast-2"
}

data "aws_ecr_repository" "existing_ecr" {
  name = "sentiment-lambda" 
}

resource "aws_lambda_function" "sentiment_api" {
  function_name = "sentiment-api"
  
  memory_size   = 2048 
  
  package_type  = "Image"
  image_uri     = "${data.aws_ecr_repository.existing_ecr.repository_url}:latest"
  
  role          = data.aws_lambda_function.existing_lambda_info.role
}

data "aws_lambda_function" "existing_lambda_info" {
  function_name = "sentiment-api"
}

output "lambda_arn" {
  value = data.aws_lambda_function.existing_lambda_info.arn
}

resource "aws_s3_bucket" "model_bucket" {
  bucket = "sentiment-model-storage-jambread" 
}

resource "aws_s3_bucket_public_access_block" "model_bucket_block" {
  bucket = aws_s3_bucket.model_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "lambda_s3_readonly" {
  name = "lambda_s3_readonly_policy"
  role = element(split("/", data.aws_lambda_function.existing_lambda_info.role), length(split("/", data.aws_lambda_function.existing_lambda_info.role)) - 1)

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = ["s3:GetObject", "s3:ListBucket"]
        Effect   = "Allow"
        Resource = [
          "${aws_s3_bucket.model_bucket.arn}",
          "${aws_s3_bucket.model_bucket.arn}/*"
        ]
      }
    ]
  })
}

