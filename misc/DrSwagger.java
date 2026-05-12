package com.digitalreef.qa.rest;

import com.google.common.base.Splitter;
import com.google.common.io.Files;
import com.google.common.io.Resources;

import com.digitalreef.qa.config.accounts.AppType;

import org.apache.commons.io.FileUtils;
import org.apache.http.client.utils.URIBuilder;
import org.springframework.util.FileSystemUtils;

import java.io.File;
import java.io.IOException;
import java.net.URI;
import java.net.URISyntaxException;
import java.net.URL;
import java.nio.file.Paths;
import java.util.List;
import java.util.Objects;

import static com.digitalreef.qa.config.properties.PropertiesConfigManager.envConfig;
import static com.digitalreef.qa.config.properties.PropertiesConfigManager.testConfig;

public enum DrSwagger {
	ADMIN(AppType.ADMIN),
	EDISCOVERY(AppType.EDISCOVERY),
	REVIEW(AppType.REVIEW);

	private final String url;
	private final String swaggerFileName;
	private final String resourceName;

	DrSwagger(AppType app) {
		swaggerFileName = app.type().toLowerCase() + ".json";
		url = app.getUrl() + swaggerFileName;
		resourceName = "swagger" + envConfig().fileSeparator() + swaggerFileName;
		setSwaggerFile();
	}

	public File getSwaggerFile() {
		URI swaggerResource;
		try {
			swaggerResource = Resources.getResource(resourceName).toURI();
		} catch (URISyntaxException e) {
			throw new IllegalArgumentException(
					String.format("Resource URL [%s] is invalid", resourceName), e);
		}
		return Paths.get(swaggerResource).toFile();
	}

	private File tempFile(String fileName) {
		List<String> fileNameParts = Splitter.on(".")
				.omitEmptyStrings()
				.trimResults()
				.splitToList(fileName);
		try {
			return File.createTempFile(fileNameParts.get(0), fileNameParts.get(1));
		} catch (IOException e) {
			throw new IllegalArgumentException(
					String.format("Issues creating temp file [%s]", fileName), e);
		}
	}

	private void setSwaggerFile() {
		File swaggerTempFile = null;
		String fileSeparator = envConfig().fileSeparator();

		try {
			SSLUtilities.trustAllHostnames();
			SSLUtilities.trustAllHttpsCertificates();

			URL url = new URIBuilder(this.url).build().toURL();
			swaggerTempFile = tempFile(swaggerFileName);
			FileUtils.copyURLToFile(url, swaggerTempFile, 15000, 15000);

			URI swaggerResourceUri = Resources.getResource(resourceName).toURI();
			File swaggerResourceFile = Paths.get(swaggerResourceUri).toFile();

			String swaggerActualPath = swaggerResourceUri.getPath()
					.replace("target", "src")
					.replace("classes", "main" + fileSeparator + "resources");

			URI swaggerActualUri = new URIBuilder()
					.setScheme(swaggerResourceUri.getScheme())
					.setPath(swaggerActualPath)
					.build();
			File swaggerActualFile = Paths.get(swaggerActualUri).toFile();

			// Overwrite the swagger resource file if different for next time, this will keep the
			// swagger files up to date depending on the system you are on and
			if (swaggerResourceFile.exists() &&
					!Files.equal(swaggerTempFile, swaggerResourceFile)) {
				Files.copy(swaggerTempFile, swaggerResourceFile);
				Files.copy(swaggerResourceFile, swaggerActualFile);
			}

		} catch (URISyntaxException e) {
			throw new IllegalArgumentException(
					String.format("URL [%s] or Resource URL [%s] is invalid",
							this.url, resourceName), e);
		} catch (IOException e) {
			throw new IllegalArgumentException(
					String.format("URL [%s] is invalid or Issues copying file [%s] from url [%s]",
							this.url, swaggerFileName, this.url), e);
		} finally {
			if (Objects.nonNull(swaggerTempFile)) {
				FileSystemUtils.deleteRecursively(swaggerTempFile);
			}
		}
	}


}
