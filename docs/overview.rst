Overview
========






This package aims to abstract away common boilerplate and integrate various foundational
components, allowing developers to focus on core business logic.

This toolkit encompasses several key areas to facilitate backend system development:

* :doc:`saigon.aws`: This sub-package provides seamless integration with various Amazon Web Services.

    * **Cognito Client** (:mod:`saigon.aws.cognito`): Offers high-level clients for managing user authentication
        via AWS Cognito User Pools (Identity Provider) and obtaining temporary IAM credentials
        from Identity Pools. This includes user creation, deletion, confirmation, and login flows.
    * **S3 Utilities** (:mod:`saigon.aws.s3`): Contains helper functions for common Amazon S3 operations,
        such as downloading objects to local files, unzipping S3 archives, uploading raw bytes,
        and generating S3 object URLs.
    * **Secrets Manager** (:mod:`saigon.aws.secrets`): Simplifies the retrieval of secrets stored in
        AWS Secrets Manager, allowing them to be directly deserialized into Pydantic models.
    * **SQS to RDS Forwarder** (:mod:`sqs.SqsToRdsForwarder`): A generic component designed
        to consume messages from an SQS queue and forward their parsed contents
        as structured data into an RDS database using SQLAlchemy.

* :doc:`saigon.fastapi`: Dedicated utilities for building high-performance web APIs with FastAPI.

    * **Utilities** (:mod:`fastapi.utils`): Includes middleware for enhanced logging and
        request context management, custom exception handlers for Pydantic validation errors,
        and helper functions for FastAPI application setup and routing.
    * **Headers & Context** (:mod:`fastapi.headers`): Defines standard header parsing for
        request context information (like API request IDs and Cognito identity IDs) and
        provides a structured :class:`saigon.fastapi.headers.RequestContext` model.

* :doc:`saigon.orm`: Focuses on Object-Relational Mapping (ORM) and database connection management.

    * **Database Connector** (:mod:`orm.connection`): Provides a foundation for establishing
        and managing database connections, typically for relational databases like PostgreSQL
        or MySQL, used for executing SQL statements and transactions.

* :mod:`saigon.model`: Contains core Pydantic data models used across different
      components of the package. These models ensure consistent data structures for API
      requests/responses, database interactions, and inter-service communication.

* :doc:`saigon.rest`: Provides abstract and concrete REST API client implementations.

    * **Base REST Client** (:mod:`saigon.rest.client.RestClientBase`): A foundational class for
        making HTTP requests to RESTful services, including utilities for waiting
        on conditions and handling S3 pre-signed URL uploads.
    * **Authenticated REST Clients** (:mod:`saigon.rest.client.AuthRestClient`): Extensions of the base client
        that integrate directly with the "mod:`saigon.aws.cognito` module to handle user authentication
        and automatically sign outgoing API requests using AWS Signature Version 4 (SigV4).

Project Status
--------------

This project is currently under active development. Features are being continuously added,
refined, and tested. While the core components are functional, it is not yet considered
officially released and may undergo significant changes. Use in production environments
is at your own discretion.