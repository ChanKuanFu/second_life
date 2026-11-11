plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.secondlife.app"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.secondlife.app"
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"
        val webUrl = providers.gradleProperty("secondlifeWebUrl").orElse("http://10.0.2.2:5000/").get()
        buildConfigField("String", "WEB_URL", "\"$webUrl\"")
    }
    buildFeatures { buildConfig = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation("androidx.activity:activity-ktx:1.10.1")
}
